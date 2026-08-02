/* ═══════════════════════════════════════════════════════════════
   АдыГид — админка.

   Три раздела (статьи / маршруты / места) живут как отдельные «экраны»:
   в один момент времени виден ровно один .view. Карта открывается только
   когда она реально нужна (правка геометрии маршрута или установка точки),
   а не висит фоном под всеми формами.
   ═══════════════════════════════════════════════════════════════ */

// Картинки лид-магнита отдаются с недельным кэшем (см. main.py) — без метки
// версии админ мог бы менять файл и не видеть разницы в предпросмотре,
// пока не протухнет кэш браузера. Одна метка на загрузку страницы, а не на
// каждую перерисовку — иначе каждая буква в поле заново качала бы картинку.
const ADMIN_ASSET_BUST = Date.now();

// ── Справочники ────────────────────────────────────────────────
const DIFFICULTY_OPTS = [
  { code: 'easy',    label: 'Лёгкая' },
  { code: 'medium',  label: 'Средняя' },
  { code: 'hard',    label: 'Сложная' },
  { code: 'extreme', label: 'Экстремальная' },
];
const SURFACE_OPTS = [
  { code: 'asphalt',  label: 'Асфальт' },
  { code: 'dirt',     label: 'Грунтовка' },
  { code: 'trail',    label: 'Тропа' },
  { code: 'scramble', label: 'Курумник / скалы' },
];
const SEASON_OPTS = [
  { code: 'year_round',  label: 'Круглый год' },
  { code: 'summer_only', label: 'Только летом (зимой снег)' },
];
const ACCESS_OPTS = [
  { code: 'paved',          label: 'Асфальт до старта' },
  { code: 'high_clearance', label: 'Грунтовка, нужен клиренс' },
  { code: 'foot_only',      label: 'Только пешком от трассы' },
];
const DISTRICT_OPTS = [
  { code: 'maikop',      label: 'Округ Майкопа' },
  { code: 'khadzhokh',   label: 'Округ Хаджоха' },
  { code: 'dakhovskaya', label: 'Округ Даховской' },
  { code: 'lagonaki',    label: 'Плато Лагонаки' },
  { code: 'guzeripl',    label: 'Округ Гузерипля' },
];
const POPULARITY_OPTS = [
  { code: 'normal',  label: 'Обычное' },
  { code: 'popular', label: 'Популярное' },
  { code: 'top',     label: 'Топ — с бейджем на карточке' },
];
const DIFF_COLOR = { easy: '#02BA27', medium: '#ED9F03', hard: '#B01111', extreme: '#650707' };

// ── Состояние ──────────────────────────────────────────────────
let categories = [];
let trails = [];
let checkpoints = [];   // все точки (и отдельные, и внутри маршрутов)
let articles = [];
let equipmentTags = [];
let scenarios = [];
let magnets = [];
let faqSets = [];
let sitePages = [];

let activeTrail = null;      // маршрут, открытый в редакторе карты
let map = null, placeMap = null;
let drawnItems = null;
let segLayers = {}, cpLayers = {};
let drawMode = null;         // 'segment' | 'point' | 'place'
let pendingPointIndex = null;   // куда вставить новую точку маршрута
let placePickCallback = null;

let articleQuill = null;
let descQuill = null;        // редактор описания в модалке маршрута/места
let editingArticleId = null;
let autosaveTimer = null;

let modalSaveHandler = null;

// ── Мелкие помощники ───────────────────────────────────────────
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function escAttr(s) { return escHtml(s).replace(/"/g, '&quot;'); }

function toast(message, isError) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.toggle('err', !!isError);
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 3200);
}

async function api(method, path, body) {
  try {
    const res = await fetch('/api' + path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const text = await res.text();
      toast('Ошибка: ' + text.slice(0, 160), true);
      return null;
    }
    return res.status === 204 ? true : await res.json();
  } catch (e) {
    toast('Нет связи с сервером', true);
    return null;
  }
}

async function uploadFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/uploads/photo', { method: 'POST', body: fd });
  if (!res.ok) { toast('Не удалось загрузить фото', true); return null; }
  return res.json();
}

function optionsHtml(opts, selected) {
  return opts.map(o => `<option value="${o.code}" ${o.code === selected ? 'selected' : ''}>${escHtml(o.label)}</option>`).join('');
}

function districtOptionsHtml(selected) {
  return `<option value="">— не указан —</option>` + optionsHtml(DISTRICT_OPTS, selected);
}

function categoryOptionsHtml(kind, selected) {
  // Служебные категории показываем, но помечаем — иначе легко случайно
  // выбрать «Стоянку» и потерять объект из фильтров на сайте.
  const fit = categories.filter(c => c.type === kind || c.type === 'both');
  const pub = fit.filter(c => c.is_public);
  const svc = fit.filter(c => !c.is_public);
  let html = `<option value="">— без категории —</option>`;
  if (pub.length) {
    html += `<optgroup label="Показываются в фильтрах на сайте">` +
      pub.map(c => `<option value="${c.id}" ${c.id === selected ? 'selected' : ''}>${escHtml((c.icon || '') + ' ' + c.name)}</option>`).join('') +
      `</optgroup>`;
  }
  if (svc.length) {
    html += `<optgroup label="Служебные — только для админки">` +
      svc.map(c => `<option value="${c.id}" ${c.id === selected ? 'selected' : ''}>${escHtml((c.icon || '') + ' ' + c.name)}</option>`).join('') +
      `</optgroup>`;
  }
  return html;
}

function categoryLabel(cat) {
  if (!cat) return 'Без категории';
  return ((cat.icon || '') + ' ' + cat.name).trim();
}

function formatDuration(minutes) {
  if (!minutes) return '';
  const h = Math.floor(minutes / 60), m = minutes % 60;
  if (h && m) return `${h} ч ${m} мин`;
  if (h) return `${h} ч`;
  return `${m} мин`;
}

function autoGrow(el) {
  el.style.height = 'auto';
  el.style.height = el.scrollHeight + 'px';
}

// ── Модалка ────────────────────────────────────────────────────
function showModal(title, bodyHtml, onSave, opts) {
  opts = opts || {};
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHtml;
  document.getElementById('modal').classList.toggle('modal-wide', !!opts.wide);
  document.getElementById('modal-foot').style.display = opts.hideFooter ? 'none' : '';
  document.getElementById('modal-save').textContent = opts.saveLabel || 'Сохранить';

  // Кнопка предпросмотра живёт слева в подвале модалки и появляется только
  // там, где есть что показывать.
  const old = document.getElementById('modal-preview');
  if (old) old.remove();
  if (opts.preview) {
    const btn = document.createElement('button');
    btn.id = 'modal-preview';
    btn.className = 'btn btn-ghost';
    btn.textContent = 'Предпросмотр';
    btn.onclick = opts.preview;
    document.getElementById('modal-foot').prepend(btn);
  }

  modalSaveHandler = onSave;
  document.getElementById('modal-backdrop').hidden = false;
}

// ── Предпросмотр в вёрстке сайта ───────────────────────────────
// HTML собирает сервер тем же кодом, что и публичную страницу, а стили
// берём из настоящего /assets/site.css — поэтому предпросмотр не может
// разъехаться с реальным сайтом.
async function openPreview(kind, html, heading, eyebrow) {
  const res = await api('POST', '/preview', { kind, html: html || '' });
  if (!res) return;

  const bodyClass = kind === 'article' ? 'article-body' : 'detail-body';
  const titleClass = kind === 'article' ? 'article-title' : 'page-title';
  const doc = `<!doctype html><html lang="ru"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="/assets/site.css">
    <style>body{background:#fff}main{padding:28px 0}</style></head>
    <body><main><section class="section" style="padding:0"><div class="wrap">
      ${eyebrow ? `<p class="eyebrow">${escHtml(eyebrow)}</p>` : ''}
      ${heading ? `<h1 class="${titleClass}">${escHtml(heading)}</h1>` : ''}
      <div class="${bodyClass}">${res.html}</div>
    </div></section></main></body></html>`;

  const frame = document.getElementById('preview-frame');
  frame.srcdoc = doc;
  document.getElementById('preview-backdrop').hidden = false;
}

function closePreview() {
  document.getElementById('preview-backdrop').hidden = true;
  document.getElementById('preview-frame').srcdoc = '';
}

function closeModal() {
  document.getElementById('modal-backdrop').hidden = true;
  modalSaveHandler = null;
}

document.getElementById('modal-save').addEventListener('click', async () => {
  if (modalSaveHandler) await modalSaveHandler();
});

// ── Второе, стековое модальное окно ─────────────────────────────
// Нужно для форм, которые открываются поверх уже открытой модалки
// (например «Что учесть» поверх формы маршрута/места/сценария) —
// общая модалка одна, и её нельзя переиспользовать для вложенного диалога.
let modal2SaveHandler = null;

function showModal2(title, bodyHtml, onSave, opts) {
  opts = opts || {};
  document.getElementById('modal2-title').textContent = title;
  document.getElementById('modal2-body').innerHTML = bodyHtml;
  document.getElementById('modal2-save').textContent = opts.saveLabel || 'Сохранить';
  modal2SaveHandler = onSave;
  document.getElementById('modal2-backdrop').hidden = false;
}

function closeModal2() {
  document.getElementById('modal2-backdrop').hidden = true;
  modal2SaveHandler = null;
}

document.getElementById('modal2-save').addEventListener('click', async () => {
  if (modal2SaveHandler) await modal2SaveHandler();
});

// ── Вкладки / экраны ───────────────────────────────────────────
// Подэкраны (редактор статьи, карта) — не отдельные вкладки: подсвечиваем
// раздел, из которого пришли, чтобы не терялась ориентация.
const TAB_OF_VIEW = {
  'article-editor': 'articles',
  'route-editor': 'routes',
  'route-map': 'routes',
  'place-map': 'places',
  'place-editor': 'places',
  'scenario-editor': 'scenarios',
};

// ── Слоты общих виджетов (desc-редактор Quill, блок критериев) ──────────
// #desc-editor и id-шники criteriaHtml() (m-difficulty и т.п.) не уникальны
// по конструкции — раньше это было безопасно, потому что раньше их строил
// только showModal(), а модалка всегда ровно одна. Теперь редактор сценария
// и маршрута — постоянные вкладки, и их разметка не уничтожается при уходе
// на другую вкладку, поэтому перед тем как разместить виджет в новом месте,
// нужно явно убрать его копию из всех остальных мест — иначе на странице
// одновременно окажутся два элемента с одним id, и getElementById достанет
// не тот. ──
const DESC_EDITOR_SLOTS = ['sc-desc-slot', 'rt-desc-slot', 'pl-desc-slot', 'modal-body'];
const CRITERIA_SLOTS = ['rt-criteria-slot', 'pl-criteria-slot', 'modal-body'];

function releaseSlots(slotIds, exceptId) {
  slotIds.forEach(id => {
    if (id === exceptId) return;
    const host = document.getElementById(id);
    if (host && host.children.length) host.innerHTML = '';
  });
}

function showTab(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + name).classList.add('active');
  const highlight = TAB_OF_VIEW[name] || name;
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === highlight);
  });
  window.scrollTo(0, 0);
}

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => showTab(tab.dataset.tab));
});

// ═══════════════════════════════════════════════════════════════
//  КАТЕГОРИИ
// ═══════════════════════════════════════════════════════════════

function openCategories() {
  const rows = categories.map(c => `
    <div class="row" style="padding:10px 12px">
      <div class="row-main">
        <div class="row-title">${escHtml(categoryLabel(c))}
          ${c.is_public ? '' : '<span class="badge badge-muted">служебная</span>'}
        </div>
        <div class="row-meta">${c.type === 'both' ? 'места и маршруты' : c.type === 'trail' ? 'маршруты' : 'места'}</div>
      </div>
      <div class="row-actions">
        <button class="btn btn-ghost btn-sm" onclick='openCategoryForm(${JSON.stringify(c)})'>Изменить</button>
        <button class="btn btn-danger btn-sm" onclick="deleteCategory(${c.id})">Удалить</button>
      </div>
    </div>`).join('');

  showModal('Категории', `
    <div class="hint" style="margin-bottom:14px;color:var(--muted);font-size:13px">
      Публичные категории — это фильтры на сайте. Служебные нужны только внутри админки
      и на сайте не показываются.
    </div>
    <div class="list">${rows || '<div class="empty">Категорий пока нет</div>'}</div>
    <button class="btn btn-ghost" style="margin-top:14px" onclick="openCategoryForm(null)">+ Новая категория</button>
  `, null, { hideFooter: true, wide: true });
}

function openCategoryForm(cat) {
  const c = cat || {};
  showModal(cat ? 'Изменить категорию' : 'Новая категория', `
    <div class="field"><label>Название</label><input id="c-name" value="${escAttr(c.name || '')}" placeholder="Водопад"></div>
    <div class="field"><label>Иконка (эмодзи)</label><input id="c-icon" value="${escAttr(c.icon || '')}" placeholder="💧"></div>
    <div class="field"><label>Где доступна</label>
      <select id="c-type">
        <option value="checkpoint" ${c.type === 'checkpoint' ? 'selected' : ''}>Только места</option>
        <option value="trail" ${c.type === 'trail' ? 'selected' : ''}>Только маршруты</option>
        <option value="both" ${c.type === 'both' ? 'selected' : ''}>И места, и маршруты</option>
      </select>
    </div>
    <label class="toggle">
      <input type="checkbox" id="c-public" ${c.is_public !== false ? 'checked' : ''}>
      <span class="toggle-track"></span>
      <span class="toggle-label">Показывать в фильтрах на сайте
        <small>Выключите для служебных меток вроде «Начало маршрута»</small>
      </span>
    </label>
  `, async () => {
    const payload = {
      name: document.getElementById('c-name').value.trim(),
      icon: document.getElementById('c-icon').value.trim() || null,
      type: document.getElementById('c-type').value,
      is_public: document.getElementById('c-public').checked,
    };
    if (!payload.name) { toast('Введите название', true); return; }
    const saved = cat
      ? await api('PATCH', `/categories/${cat.id}`, payload)
      : await api('POST', '/categories', payload);
    if (saved) { await loadAll(); closeModal(); toast('Категория сохранена'); }
  });
}

async function deleteCategory(id) {
  if (!confirm('Удалить категорию? У объектов с ней категория станет пустой.')) return;
  await api('DELETE', `/categories/${id}`);
  await loadAll();
  openCategories();
}

// ── Редактор описания внутри модалки (маршрут / место / сценарий) ──
// Тот же самый набор возможностей, что и в редакторе статей: плавающая «+»
// у курсора и панель вставки внизу — фото, коллаж, ссылка, лид-магнит,
// набор вопросов, «Что учесть». Диалоги вставки открываются во второй,
// стековой модалке (showModal2) — общая модалка тут уже занята формой
// маршрута/места/сценария.
function descEditorHtml(label) {
  return `<div class="field desc-field">
    <label>${label}</label>
    <div class="hint" style="margin:0 0 6px">Выделите текст, чтобы сделать заголовок, список или ссылку.</div>
    <div class="desc-editor-wrap">
      <div class="editor-wrap">
        <button type="button" class="insert-plus" id="desc-insert-plus"
                title="Вставить фото, коллаж или ссылку" onclick="toggleDescInsertMenu(event)">+</button>
        <div class="insert-menu" id="desc-insert-menu" hidden>
          <button type="button" onclick="runDescInsert('photo')"><span>🖼</span> Фото с подписью</button>
          <button type="button" onclick="runDescInsert('collage')"><span>▥</span> Коллаж 2–4 фото</button>
          <button type="button" onclick="runDescInsert('link')"><span>🔗</span> Ссылка на место, маршрут, статью или сценарий</button>
          <button type="button" onclick="runDescInsert('magnet')"><span>🎁</span> Лид-магнит</button>
          <button type="button" onclick="runDescInsert('faq')"><span>❓</span> Набор вопросов</button>
          <button type="button" onclick="runDescInsert('consider')"><span>☑️</span> Что учесть</button>
        </div>
        <div id="desc-editor"></div>
      </div>
    </div>
    <div class="insert-bar">
      <span class="insert-bar-label">Вставить в текст:</span>
      <button type="button" class="btn btn-ghost btn-sm" onclick="insertPhoto(descQuill)">Фото</button>
      <button type="button" class="btn btn-ghost btn-sm" onclick="insertCollage(descQuill)">Коллаж 2–4 фото</button>
      <button type="button" class="btn btn-ghost btn-sm" onclick="insertInternalLink(descQuill)">Ссылка на объект</button>
      <button type="button" class="btn btn-ghost btn-sm" onclick="insertMagnet(descQuill)">Лид-магнит</button>
      <button type="button" class="btn btn-ghost btn-sm" onclick="insertFaqSet(descQuill)">Набор вопросов</button>
      <button type="button" class="btn btn-ghost btn-sm" onclick="insertConsiderBlock(descQuill)">Что учесть</button>
    </div>
  </div>`;
}

// ── Автосохранение черновика desc-редактора в localStorage ──────
// Тот же риск, что и со статьями: модалку можно закрыть по клику мимо или
// случайно перезагрузить вкладку, потеряв неотправленный текст маршрута,
// места или сценария. scope — «route:12», «place:new», «scenario:3» и т.п.,
// отдельный для каждой открытой формы.
let descDraftScope = null;
let descAutosaveTimer = null;

function descDraftKey(scope) { return 'adygid_draft_desc_' + scope; }

function scheduleDescAutosave() {
  if (!descDraftScope) return;
  clearTimeout(descAutosaveTimer);
  descAutosaveTimer = setTimeout(() => {
    try {
      const html = readDescEditor();
      if (html) localStorage.setItem(descDraftKey(descDraftScope), JSON.stringify({ savedAt: Date.now(), html }));
      else localStorage.removeItem(descDraftKey(descDraftScope));
    } catch (e) {
      // приватный режим — просто не сохраняем
    }
  }, 1200);
}

function clearDescDraft(scope) {
  try { localStorage.removeItem(descDraftKey(scope)); } catch (e) { /* no-op */ }
}

function initDescEditor(html, scope) {
  registerEmbedBlots();
  descDraftScope = scope || null;
  descQuill = new Quill('#desc-editor', {
    theme: 'bubble',
    placeholder: 'Описание — что это за место, как добраться, что учесть...',
    modules: {
      toolbar: [
        ['bold', 'italic', 'link'],
        [{ header: [2, 3, false] }],
        [{ list: 'ordered' }, { list: 'bullet' }],
      ],
    },
  });
  descQuill.setContents([], 'silent');
  if (html) descQuill.clipboard.dangerouslyPasteHTML(0, html, 'silent');

  if (descDraftScope) {
    let draft = null;
    try { const raw = localStorage.getItem(descDraftKey(descDraftScope)); draft = raw ? JSON.parse(raw) : null; } catch (e) { /* no-op */ }
    if (draft && draft.html && draft.html !== (html || null)) {
      const when = new Date(draft.savedAt).toLocaleString('ru-RU');
      if (confirm(`Найден несохранённый черновик текста от ${when}. Восстановить его?`)) {
        descQuill.setContents([], 'silent');
        descQuill.clipboard.dangerouslyPasteHTML(0, draft.html, 'silent');
      } else {
        clearDescDraft(descDraftScope);
      }
    }
  }

  descQuill.on('editor-change', positionDescInsertPlus);
  descQuill.on('text-change', scheduleDescAutosave);
}

// ── Плавающая кнопка вставки для desc-редактора — тот же принцип, что и
// у статьи (positionInsertPlus/toggleInsertMenu), но свои id, потому что
// оба редактора могут одновременно жить в DOM (страница статьи в фоне). ──
function positionDescInsertPlus() {
  const plus = document.getElementById('desc-insert-plus');
  if (!plus || !descQuill) return;
  const range = descQuill.getSelection();
  if (!range) { plus.classList.remove('visible'); hideDescInsertMenu(); return; }
  const bounds = descQuill.getBounds(range.index, 0);
  plus.style.top = bounds.top + 'px';
  plus.classList.add('visible');
}

function toggleDescInsertMenu(e) {
  e.stopPropagation();
  const menu = document.getElementById('desc-insert-menu');
  const plus = document.getElementById('desc-insert-plus');
  if (!menu.hidden) { hideDescInsertMenu(); return; }
  menu.style.top = (parseFloat(plus.style.top || 0) + 36) + 'px';
  menu.hidden = false;
}

function hideDescInsertMenu() {
  const menu = document.getElementById('desc-insert-menu');
  if (menu) menu.hidden = true;
}

function runDescInsert(kind) {
  hideDescInsertMenu();
  if (kind === 'photo') insertPhoto(descQuill);
  else if (kind === 'collage') insertCollage(descQuill);
  else if (kind === 'magnet') insertMagnet(descQuill);
  else if (kind === 'faq') insertFaqSet(descQuill);
  else if (kind === 'consider') insertConsiderBlock(descQuill);
  else insertInternalLink(descQuill);
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('#desc-insert-menu') && !e.target.closest('#desc-insert-plus')) hideDescInsertMenu();
});

function readDescEditor() {
  if (!descQuill) return null;
  const clone = descQuill.root.cloneNode(true);
  clone.querySelectorAll('.magnet-embed, .faq-embed, .consider-embed').forEach(el => { el.innerHTML = ''; });
  const html = clone.innerHTML.trim();
  // Пустой Quill отдаёт <p><br></p> — на сайте это лишний пустой абзац.
  return (!html || html === '<p><br></p>') ? null : html;
}

// ═══════════════════════════════════════════════════════════════
//  ОБЩИЙ БЛОК КРИТЕРИЕВ (маршрут и место) — сгруппирован
// ═══════════════════════════════════════════════════════════════

function criteriaHtml(v, opts) {
  v = v || {};
  opts = opts || {};
  const surfaces = v.surface_types || [];
  return `
  <details class="group" open>
    <summary>Сложность и доступ</summary>
    <div class="group-body">
      <div class="field-row">
        <div class="field"><label>Сложность</label>
          <select id="m-difficulty">${optionsHtml(DIFFICULTY_OPTS, v.difficulty || 'medium')}</select>
        </div>
        <div class="field"><label>Как добраться</label>
          <select id="m-access">${optionsHtml(ACCESS_OPTS, v.access_type || 'foot_only')}</select>
        </div>
      </div>
      <div class="field" style="margin-bottom:0"><label>Покрытие</label>
        <div class="chips">
          ${SURFACE_OPTS.map(o => `<label class="chip"><input type="checkbox" class="m-surface" value="${o.code}" ${surfaces.includes(o.code) ? 'checked' : ''}><span>${escHtml(o.label)}</span></label>`).join('')}
        </div>
      </div>
    </div>
  </details>

  <details class="group">
    <summary>Условия и снаряжение</summary>
    <div class="group-body">
      <div class="field-row">
        <div class="field"><label>Сезонность</label>
          <select id="m-season">${optionsHtml(SEASON_OPTS, v.seasonality || 'year_round')}</select>
        </div>
        <div class="field"><label>Комментарий по цене</label>
          <input id="m-price-note" value="${escAttr(v.price_note || '')}" placeholder="300₽ с человека">
        </div>
      </div>
      <div class="field"><label>Снаряжение (через запятую)</label>
        <input id="m-equipment" list="equipment-list" value="${escAttr((v.equipment_tags || []).join(', '))}" placeholder="треккинговые палки, ветровка">
        <datalist id="equipment-list">${equipmentTags.map(t => `<option value="${escAttr(t)}">`).join('')}</datalist>
      </div>
      <label class="toggle" style="margin-bottom:12px">
        <input type="checkbox" id="m-paid" ${v.is_paid ? 'checked' : ''}>
        <span class="toggle-track"></span><span class="toggle-label">Платный вход</span>
      </label>
      <label class="toggle" style="margin-bottom:12px">
        <input type="checkbox" id="m-kid" ${v.kid_friendly ? 'checked' : ''}>
        <span class="toggle-track"></span>
        <span class="toggle-label">Подходит с детьми<small>Ребёнок пройдёт сам или на руках по всей тропе</small></span>
      </label>
      <label class="toggle">
        <input type="checkbox" id="m-weather" ${v.weather_warning ? 'checked' : ''}>
        <span class="toggle-track"></span>
        <span class="toggle-label">Осторожно после дождя<small>Показывается предупреждением, фильтром не является</small></span>
      </label>
    </div>
  </details>

  <details class="group">
    <summary>Публикация на сайте</summary>
    <div class="group-body">
      <div class="field-row">
        <div class="field"><label>Округ</label>
          <select id="m-district">${districtOptionsHtml(v.district)}</select>
        </div>
        <div class="field"><label>Популярность</label>
          <select id="m-popularity">${optionsHtml(POPULARITY_OPTS, v.popularity || 'normal')}</select>
        </div>
      </div>
      ${opts.extraPublishHtml || ''}
    </div>
  </details>`;
}

function readCriteria() {
  return {
    difficulty: document.getElementById('m-difficulty').value,
    access_type: document.getElementById('m-access').value,
    surface_types: Array.from(document.querySelectorAll('.m-surface:checked')).map(el => el.value),
    seasonality: document.getElementById('m-season').value,
    price_note: document.getElementById('m-price-note').value.trim() || null,
    equipment_tags: document.getElementById('m-equipment').value.split(',').map(s => s.trim()).filter(Boolean),
    is_paid: document.getElementById('m-paid').checked,
    kid_friendly: document.getElementById('m-kid').checked,
    weather_warning: document.getElementById('m-weather').checked,
    district: document.getElementById('m-district').value || null,
    popularity: document.getElementById('m-popularity').value,
  };
}

// ═══════════════════════════════════════════════════════════════
//  СТАТЬИ
// ═══════════════════════════════════════════════════════════════

function renderArticles() {
  const q = (document.getElementById('articles-search').value || '').toLowerCase();
  const list = articles.filter(a => !q || a.title.toLowerCase().includes(q));
  const el = document.getElementById('articles-list');
  if (!list.length) {
    el.innerHTML = `<div class="empty"><b>Статей нет</b>Нажмите «Новая статья», чтобы написать первую.</div>`;
    return;
  }
  el.innerHTML = list.map(a => `
    <div class="row">
      <div class="row-thumb" style="${a.cover_url ? `background-image:url('${escAttr(a.cover_url)}')` : ''}"></div>
      <div class="row-main">
        <div class="row-title">${escHtml(a.title)}
          ${a.is_published ? '' : '<span class="badge badge-draft">черновик</span>'}
          ${(a.faq && a.faq.length) ? `<span class="badge">FAQ · ${a.faq.length}</span>` : ''}
        </div>
        <div class="row-meta">
          <span>/stati/${escHtml(a.slug)}</span>
          ${a.district ? `<span>${escHtml((DISTRICT_OPTS.find(d => d.code === a.district) || {}).label || a.district)}</span>` : ''}
        </div>
      </div>
      <div class="row-actions">
        <a class="btn btn-ghost btn-sm" href="/stati/${escAttr(a.slug)}" target="_blank" rel="noopener">Открыть</a>
        <button class="btn btn-ghost btn-sm" onclick="openArticleEditor(${a.id})">Редактировать</button>
        <button class="btn btn-danger btn-sm" onclick="deleteArticle(${a.id})">Удалить</button>
      </div>
    </div>`).join('');
}

function draftKey(id) { return 'adygid_draft_article_' + (id || 'new'); }

// ── Живой предпросмотр обложки — файл или ссылка, что заполнено последним.
// Статью редактирует один и тот же постоянный DOM (не пересоздаётся при
// каждом открытии, в отличие от модалок), поэтому вешаем слушатели один раз
// (dataset-флаг) и на каждый вызов только обновляем картинку. ──
function setupCoverPreview(fileId, urlId, previewId) {
  const fileEl = document.getElementById(fileId);
  const urlEl = document.getElementById(urlId);
  const boxEl = document.getElementById(previewId);
  if (!fileEl || !urlEl || !boxEl) return;
  const imgEl = boxEl.querySelector('img');
  const update = () => {
    if (fileEl.files.length) {
      imgEl.src = URL.createObjectURL(fileEl.files[0]);
      boxEl.hidden = false;
    } else if (urlEl.value.trim()) {
      imgEl.src = urlEl.value.trim();
      boxEl.hidden = false;
    } else {
      boxEl.hidden = true;
      imgEl.removeAttribute('src');
    }
  };
  if (!fileEl.dataset.previewBound) {
    fileEl.addEventListener('change', update);
    urlEl.addEventListener('input', update);
    fileEl.dataset.previewBound = '1';
  }
  update();
}

function setArticleBody(html) {
  // Только через clipboard-парсер Quill: прямое присваивание root.innerHTML
  // редактор не разбирает в свою модель, и часть разметки (списки в первую
  // очередь) молча теряется при первом же сохранении.
  articleQuill.setContents([], 'silent');
  if (html) articleQuill.clipboard.dangerouslyPasteHTML(0, html, 'silent');
}

function initArticleQuill() {
  if (articleQuill) return;
  registerEmbedBlots();
  articleQuill = new Quill('#article-editor', {
    theme: 'bubble',
    placeholder: 'Текст статьи. Выделите фрагмент, чтобы отформатировать.',
    modules: {
      toolbar: [
        ['bold', 'italic', 'underline', 'link'],
        [{ header: [2, 3, false] }],
        [{ list: 'ordered' }, { list: 'bullet' }],
        ['blockquote'],
      ],
    },
  });
  articleQuill.on('text-change', scheduleAutosave);
  // Кнопка «+» должна стоять напротив той строки, где сейчас курсор
  articleQuill.on('editor-change', positionInsertPlus);
}

// ── Плавающая кнопка вставки у текущей строки ──────────────────
function positionInsertPlus() {
  const plus = document.getElementById('insert-plus');
  if (!plus || !articleQuill) return;
  const range = articleQuill.getSelection();
  if (!range) { plus.classList.remove('visible'); hideInsertMenu(); return; }
  // getBounds отдаёт координаты относительно контейнера редактора, а кнопка
  // лежит в .editor-wrap с тем же верхом — значит top можно брать как есть.
  const bounds = articleQuill.getBounds(range.index, 0);
  plus.style.top = bounds.top + 'px';
  plus.classList.add('visible');
}

function toggleInsertMenu(e) {
  e.stopPropagation();
  const menu = document.getElementById('insert-menu');
  const plus = document.getElementById('insert-plus');
  if (!menu.hidden) { hideInsertMenu(); return; }
  menu.style.top = (parseFloat(plus.style.top || 0) + 36) + 'px';
  menu.hidden = false;
}

function hideInsertMenu() {
  const menu = document.getElementById('insert-menu');
  if (menu) menu.hidden = true;
}

function runInsert(kind) {
  hideInsertMenu();
  if (kind === 'photo') insertPhoto();
  else if (kind === 'collage') insertCollage();
  else if (kind === 'magnet') insertMagnet();
  else if (kind === 'faq') insertFaqSet();
  else if (kind === 'consider') insertConsiderBlock(articleQuill);
  else insertInternalLink();
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('#insert-menu') && !e.target.closest('#insert-plus')) hideInsertMenu();
});

function openArticleEditor(id) {
  editingArticleId = id;
  showTab('article-editor');
  initArticleQuill();

  const a = id ? articles.find(x => x.id === id) : null;
  document.getElementById('a-title').value = a ? a.title : '';
  document.getElementById('a-excerpt').value = a ? (a.excerpt || '') : '';
  document.getElementById('a-slug').value = a ? a.slug : '';
  document.getElementById('a-cover-url').value = a ? (a.cover_url || '') : '';
  document.getElementById('a-cover-file').value = '';
  setupCoverPreview('a-cover-file', 'a-cover-url', 'a-cover-preview');
  document.getElementById('a-published').checked = a ? a.is_published !== false : true;
  document.getElementById('a-district').innerHTML = districtOptionsHtml(a ? a.district : null);
  setArticleBody(a ? (a.body || '') : '');

  renderFaqRows(a ? (a.faq || []) : []);
  renderFeaturedPickers(a);
  autoGrow(document.getElementById('a-title'));
  setSaveState('');

  // Черновик мог остаться после случайно закрытой вкладки — предлагаем вернуть.
  const draft = readDraft(id);
  if (draft) {
    const when = new Date(draft.savedAt).toLocaleString('ru-RU');
    if (confirm(`Найден несохранённый черновик от ${when}. Восстановить его?`)) {
      applyDraft(draft);
    } else {
      clearDraft(id);
    }
  }
}

function closeArticleEditor() {
  showTab('articles');
  editingArticleId = null;
}

function setSaveState(text, saved, targetId) {
  const el = document.getElementById(targetId || 'save-state');
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('saved', !!saved);
}

// ── Автосохранение черновика в localStorage ────────────────────
function readArticleBody() {
  // В базу кладём пустые контейнеры блоков: содержимое подставляет сервер,
  // иначе в статье осела бы копия текста магнита и правки не подхватывались.
  const clone = articleQuill.root.cloneNode(true);
  clone.querySelectorAll('.magnet-embed, .faq-embed, .consider-embed').forEach(el => { el.innerHTML = ''; });
  return clone.innerHTML;
}

function collectArticleDraft() {
  return {
    savedAt: Date.now(),
    title: document.getElementById('a-title').value,
    excerpt: document.getElementById('a-excerpt').value,
    slug: document.getElementById('a-slug').value,
    cover_url: document.getElementById('a-cover-url').value,
    district: document.getElementById('a-district').value,
    is_published: document.getElementById('a-published').checked,
    body: articleQuill ? readArticleBody() : '',
    faq: readFaqRows(),
  };
}

function scheduleAutosave() {
  if (!document.getElementById('view-article-editor').classList.contains('active')) return;
  clearTimeout(autosaveTimer);
  setSaveState('Изменения не сохранены');
  autosaveTimer = setTimeout(() => {
    try {
      localStorage.setItem(draftKey(editingArticleId), JSON.stringify(collectArticleDraft()));
      setSaveState('Черновик сохранён локально', true);
    } catch (e) {
      // приватный режим — просто не сохраняем
    }
  }, 1200);
}

function readDraft(id) {
  try {
    const raw = localStorage.getItem(draftKey(id));
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

function clearDraft(id) {
  try { localStorage.removeItem(draftKey(id)); } catch (e) { /* no-op */ }
}

function applyDraft(d) {
  document.getElementById('a-title').value = d.title || '';
  document.getElementById('a-excerpt').value = d.excerpt || '';
  document.getElementById('a-slug').value = d.slug || '';
  document.getElementById('a-cover-url').value = d.cover_url || '';
  setupCoverPreview('a-cover-file', 'a-cover-url', 'a-cover-preview');
  document.getElementById('a-published').checked = d.is_published !== false;
  document.getElementById('a-district').innerHTML = districtOptionsHtml(d.district || null);
  setArticleBody(d.body || '');
  renderFaqRows(d.faq || []);
  autoGrow(document.getElementById('a-title'));
  setSaveState('Черновик восстановлен', true);
}

function previewArticle() {
  openPreview(
    'article',
    articleQuill ? readArticleBody() : '',
    document.getElementById('a-title').value.trim(),
    'Статья',
  );
}

async function saveArticle() {
  const title = document.getElementById('a-title').value.trim();
  if (!title) { toast('Введите заголовок', true); return; }

  let coverUrl = document.getElementById('a-cover-url').value.trim();
  let coverThumb = null;
  const fileEl = document.getElementById('a-cover-file');
  if (fileEl.files.length) {
    const up = await uploadFile(fileEl.files[0]);
    if (up) { coverUrl = up.url; coverThumb = up.thumb_url; }
  }

  const payload = {
    title,
    slug: document.getElementById('a-slug').value.trim() || null,
    excerpt: document.getElementById('a-excerpt').value.trim() || null,
    cover_url: coverUrl || null,
    cover_thumb_url: coverThumb,
    body: readArticleBody(),
    faq: readFaqRows(),
    district: document.getElementById('a-district').value || null,
    featured_checkpoint_ids: readPicker('a-featured-cps'),
    featured_trail_ids: readPicker('a-featured-trails'),
    is_published: document.getElementById('a-published').checked,
  };

  const saved = editingArticleId
    ? await api('PATCH', `/articles/${editingArticleId}`, payload)
    : await api('POST', '/articles', payload);
  if (!saved) return;

  clearDraft(editingArticleId);
  if (!editingArticleId) clearDraft(null);
  editingArticleId = saved.id;
  await loadAll();
  setSaveState('Сохранено на сервере', true);
  toast('Статья сохранена');
}

async function deleteArticle(id) {
  if (!confirm('Удалить статью?')) return;
  await api('DELETE', `/articles/${id}`);
  clearDraft(id);
  await loadAll();
}

// ── FAQ ────────────────────────────────────────────────────────
function faqRowHtml(item) {
  item = item || { question: '', answer: '' };
  return `<div class="faq-row">
    <div class="field"><input class="faq-q" placeholder="Вопрос" value="${escAttr(item.question)}" oninput="scheduleAutosave()"></div>
    <div class="field"><textarea class="faq-a" placeholder="Ответ" oninput="scheduleAutosave()">${escHtml(item.answer)}</textarea></div>
    <button class="btn btn-danger btn-sm" onclick="this.closest('.faq-row').remove(); scheduleAutosave()">Удалить</button>
  </div>`;
}

function renderFaqRows(items) {
  document.getElementById('a-faq-rows').innerHTML = (items || []).map(faqRowHtml).join('');
}

function addFaqRow() {
  document.getElementById('a-faq-rows').insertAdjacentHTML('beforeend', faqRowHtml());
  scheduleAutosave();
}

function readFaqRows() {
  return Array.from(document.querySelectorAll('#a-faq-rows .faq-row')).map(row => ({
    question: row.querySelector('.faq-q').value.trim(),
    answer: row.querySelector('.faq-a').value.trim(),
  })).filter(i => i.question && i.answer);
}

// ── Пикеры «места/маршруты из статьи» ──────────────────────────
function pickerHtml(items, selectedIds, labelFn) {
  const selected = selectedIds || [];
  const rows = items.map(it => `
    <label class="picker-item">
      <input type="checkbox" class="picker-check" value="${it.id}" ${selected.includes(it.id) ? 'checked' : ''} onchange="scheduleAutosave()">
      <span>${escHtml(labelFn(it))}</span>
    </label>`).join('');
  return `<div class="picker">
    <input type="text" class="picker-search" placeholder="Поиск..." oninput="filterPicker(this)">
    <div class="picker-list">${rows || '<div class="picker-empty">Пусто</div>'}</div>
  </div>`;
}

function filterPicker(input) {
  const q = input.value.trim().toLowerCase();
  input.nextElementSibling.querySelectorAll('.picker-item').forEach(item => {
    item.style.display = item.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

function readPicker(id) {
  return Array.from(document.querySelectorAll(`#${id} .picker-check:checked`)).map(el => parseInt(el.value, 10));
}

function renderFeaturedPickers(a) {
  // readPicker ищет чекбоксы внутри контейнера по его id — сам список
  // дополнительного id не требует.
  const places = checkpoints.filter(c => c.show_as_place);
  document.getElementById('a-featured-cps').innerHTML =
    pickerHtml(places, a ? a.featured_checkpoint_ids : [], c => c.name);
  document.getElementById('a-featured-trails').innerHTML =
    pickerHtml(trails, a ? a.featured_trail_ids : [], t => t.name);
}

// ── Вставка фото и ссылок в текст статьи ───────────────────────
function pickFiles(multiple) {
  return new Promise(resolve => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/jpeg,image/png,image/webp';
    input.multiple = !!multiple;
    input.onchange = () => resolve(Array.from(input.files));
    input.click();
  });
}

async function insertPhoto(quill) { await photoFlow(quill || articleQuill, false); }
async function insertCollage(quill) { await photoFlow(quill || articleQuill, true); }

function currentInsertIndex(quill) {
  // Пока курсор ни разу не ставили, вставляем в конец текста, а не в начало —
  // иначе первая же картинка окажется перед заголовком статьи.
  const range = quill.getSelection();
  return range ? range.index : quill.getLength() - 1;
}

async function photoFlow(quill, multiple) {
  // Позицию курсора запоминаем ДО открытия диалога: пока пользователь выбирает
  // файл и печатает подписи, фокус уходит из редактора, и спрашивать позицию
  // потом — значит рисковать вставкой не туда.
  const at = currentInsertIndex(quill);

  const files = await pickFiles(multiple);
  if (!files.length) return;
  const chosen = multiple ? files.slice(0, 4) : files.slice(0, 1);
  if (multiple && chosen.length < 2) { toast('Для коллажа нужно минимум 2 фото', true); return; }

  const rows = chosen.map((f, i) => `
    <div class="pickfile-item">
      <img src="${URL.createObjectURL(f)}" alt="">
      <div class="field">
        <label>Подпись к фото ${i + 1}</label>
        <input class="cap-input" placeholder="Можно оставить пустым">
      </div>
    </div>`).join('');

  // Вторая, стековая модалка — эта форма может открыться поверх уже открытой
  // (маршрут/место/сценарий), общую модалку для этого переиспользовать нельзя.
  showModal2(multiple ? 'Коллаж' : 'Фото', `<div class="pickfile">${rows}</div>`, async () => {
    const caps = Array.from(document.querySelectorAll('.cap-input')).map(el => el.value.trim());
    document.getElementById('modal2-save').disabled = true;
    document.getElementById('modal2-save').textContent = 'Загружаю...';

    const uploaded = [];
    for (let i = 0; i < chosen.length; i++) {
      const up = await uploadFile(chosen[i]);
      if (up) uploaded.push({ url: up.url, caption: caps[i] || '' });
    }
    document.getElementById('modal2-save').disabled = false;

    if (uploaded.length) {
      let index = at;
      uploaded.forEach(item => {
        quill.insertEmbed(index, 'image', item.url, 'user');
        // Quill не умеет alt из коробки — проставляем прямо в DOM редактора,
        // при сохранении он уедет вместе с картинкой (сайт делает из alt подпись).
        const imgs = quill.root.querySelectorAll(`img[src="${CSS.escape(item.url)}"]`);
        const el = imgs[imgs.length - 1];
        if (el) { el.alt = item.caption; el.title = item.caption; }
        index += 1;
      });
      quill.insertText(index, '\n', 'user');
      quill.setSelection(index + 1);
      scheduleAutosave();
    }
    closeModal2();
  }, { saveLabel: 'Вставить' });
}

function insertInternalLink(quill) {
  quill = quill || articleQuill;
  // Выделение запоминаем до открытия модалки — по той же причине, что и в photoFlow
  const savedRange = quill.getSelection();
  const at = savedRange ? savedRange.index : quill.getLength() - 1;
  const selLength = savedRange ? savedRange.length : 0;

  const places = checkpoints.filter(c => c.show_as_place);
  const rows = [
    ...places.map(p => ({ url: `/mesta/${p.id}`, label: p.name, kind: 'Место' })),
    ...trails.map(t => ({ url: `/marshruty/${t.id}`, label: t.name, kind: 'Маршрут' })),
    ...articles.map(a => ({ url: `/stati/${a.slug}`, label: a.title, kind: 'Статья' })),
    ...scenarios.map(s => ({ url: `/kuda/${s.slug}`, label: s.door, kind: 'Сценарий' })),
  ];
  if (!rows.length) { toast('Сначала добавьте места, маршруты, статьи или сценарии', true); return; }

  showModal2('Ссылка на место, маршрут, статью или сценарий', `
    <div class="picker">
      <input type="text" class="picker-search" placeholder="Поиск..." oninput="filterPicker(this)">
      <div class="picker-list">
        ${rows.map(r => `<label class="picker-item">
          <input type="radio" name="link-target" value="${escAttr(r.url)}" data-label="${escAttr(r.label)}">
          <span><b>${escHtml(r.label)}</b> — ${r.kind}</span>
        </label>`).join('')}
      </div>
    </div>`, () => {
    const picked = document.querySelector('input[name=link-target]:checked');
    if (!picked) { toast('Выберите объект', true); return; }
    if (selLength > 0) {
      // Был выделен текст — превращаем его в ссылку, не подменяя формулировку
      quill.formatText(at, selLength, 'link', picked.value, 'user');
    } else {
      const label = picked.dataset.label;
      quill.insertText(at, label, { link: picked.value }, 'user');
      quill.setSelection(at + label.length);
    }
    scheduleAutosave();
    closeModal2();
  }, { saveLabel: 'Вставить ссылку' });
}

// ═══════════════════════════════════════════════════════════════
//  МАРШРУТЫ
// ═══════════════════════════════════════════════════════════════

function renderRoutes() {
  const q = (document.getElementById('routes-search').value || '').toLowerCase();
  const list = trails.filter(t => !q || t.name.toLowerCase().includes(q));
  const el = document.getElementById('routes-list');
  if (!list.length) {
    el.innerHTML = `<div class="empty"><b>Маршрутов нет</b>Создайте маршрут, потом нарисуйте тропу на карте.</div>`;
    return;
  }
  el.innerHTML = list.map(t => {
    const cover = (t.photos && t.photos.length) ? t.photos[0].thumb_url || t.photos[0].url : '';
    const pts = t.checkpoints.length;
    const shown = t.checkpoints.filter(c => c.show_as_place).length;
    return `
    <div class="row">
      <div class="row-thumb" style="${cover ? `background-image:url('${escAttr(cover)}')` : ''}"></div>
      <div class="row-main">
        <div class="row-title">${escHtml(t.name)}
          ${t.popularity === 'top' ? '<span class="badge badge-gold">Топ</span>' : ''}
          <span class="badge badge-green">${escHtml((DIFFICULTY_OPTS.find(d => d.code === t.difficulty) || {}).label || t.difficulty)}</span>
        </div>
        <div class="row-meta">
          <span>${t.segments.length} участк. тропы</span>
          <span>${pts} точ. · ${shown} как места</span>
          ${t.duration_minutes ? `<span>${formatDuration(t.duration_minutes)}</span>` : ''}
          <span>${escHtml(categoryLabel(t.category))}</span>
        </div>
      </div>
      <div class="row-actions">
        <button class="btn btn-ghost btn-sm" onclick="openRouteForm(${t.id})">Текст и параметры</button>
        <button class="btn btn-ghost btn-sm" onclick="openRouteMap(${t.id})">Карта и точки</button>
        <button class="btn btn-ghost btn-sm" onclick="openPhotos('trail', ${t.id})">Фото (${t.photos.length})</button>
        <button class="btn btn-danger btn-sm" onclick="deleteTrail(${t.id})">Удалить</button>
      </div>
    </div>`;
  }).join('');
}

let editingRouteId = null;

function openRouteForm(id) {
  releaseSlots(DESC_EDITOR_SLOTS, 'rt-desc-slot');
  releaseSlots(CRITERIA_SLOTS, 'rt-criteria-slot');
  editingRouteId = id;
  showTab('route-editor');

  const t = id ? trails.find(x => x.id === id) : null;
  const v = t || {};

  document.getElementById('rt-name').value = v.name || '';
  document.getElementById('rt-category').innerHTML = categoryOptionsHtml('trail', v.category_id);
  document.getElementById('rt-duration').value = v.duration_minutes || '';
  document.getElementById('rt-desc-slot').innerHTML = descEditorHtml('Описание');
  document.getElementById('rt-criteria-slot').innerHTML = criteriaHtml(v);
  document.getElementById('rt-map-hint').style.display = t ? '' : 'none';

  initDescEditor(v.description || '', 'route:' + (t ? t.id : 'new'));
  autoGrow(document.getElementById('rt-name'));
  setSaveState('', false, 'rt-save-state');
}

function closeRouteEditor() {
  showTab('routes');
  editingRouteId = null;
}

function previewRoute() {
  openPreview(
    'description',
    readDescEditor() || '',
    document.getElementById('rt-name').value.trim(),
    'Маршрут',
  );
}

async function saveRoute() {
  const name = document.getElementById('rt-name').value.trim();
  if (!name) { toast('Введите название', true); return; }

  const payload = Object.assign({
    name,
    category_id: parseInt(document.getElementById('rt-category').value, 10) || null,
    duration_minutes: parseInt(document.getElementById('rt-duration').value, 10) || null,
    description: readDescEditor(),
  }, readCriteria());

  const wasNew = !editingRouteId;
  const saved = editingRouteId
    ? await api('PATCH', `/trails/${editingRouteId}`, payload)
    : await api('POST', '/trails', payload);
  if (!saved) return;

  clearDescDraft('route:' + (editingRouteId || 'new'));
  editingRouteId = saved.id;
  await loadAll();
  toast('Маршрут сохранён');
  if (wasNew) {
    // У новой тропы дальше есть только один следующий шаг — нарисовать её
    // на карте, поэтому редактор текста в этом случае закрывается сам.
    closeRouteEditor();
    openRouteMap(saved.id);
  } else {
    setSaveState('Сохранено на сервере', true, 'rt-save-state');
  }
}

function scheduleRouteAutosave() {
  if (!document.getElementById('view-route-editor').classList.contains('active')) return;
  setSaveState('Изменения не сохранены', false, 'rt-save-state');
}

async function deleteTrail(id) {
  if (!confirm('Удалить маршрут вместе с тропой, точками и фото?')) return;
  await api('DELETE', `/trails/${id}`);
  await loadAll();
}

// ── Карта маршрута ─────────────────────────────────────────────
function openRouteMap(id) {
  activeTrail = trails.find(t => t.id === id);
  if (!activeTrail) return;
  showTab('route-map');
  document.getElementById('rm-title').textContent = activeTrail.name;
  document.getElementById('rm-sub').textContent = 'Рисуйте тропу участками и расставляйте точки по пути.';
  ensureMap();
  drawTrailOnMap();
  renderSegments();
  renderPoints();
  setHint(null);
}

function setHint(text) {
  const el = document.getElementById('rm-hint');
  el.textContent = text || 'Выберите действие ниже — рисование начнётся по клику на карте.';
  el.classList.toggle('idle', !text);
}

function ensureMap() {
  if (!map) {
    map = L.map('map').setView([44.15, 40.17], 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap', maxZoom: 18,
    }).addTo(map);
    drawnItems = new L.FeatureGroup().addTo(map);

    map.on(L.Draw.Event.CREATED, async (e) => {
      const layer = e.layer;
      if (drawMode === 'segment') {
        await api('POST', `/trails/${activeTrail.id}/segments`, {
          difficulty: document.getElementById('rm-seg-difficulty').value,
          order_index: activeTrail.segments.length,
          geojson: layer.toGeoJSON().geometry,
        });
        await refreshActiveTrail();
      } else if (drawMode === 'point') {
        const ll = layer.getLatLng();
        openPointForm(null, { lat: ll.lat, lon: ll.lng, atIndex: pendingPointIndex });
      }
      drawMode = null;
      pendingPointIndex = null;
      setHint(null);
    });
  }
  setTimeout(() => map.invalidateSize(), 60);
}

function drawTrailOnMap() {
  Object.values(segLayers).forEach(l => drawnItems.removeLayer(l));
  Object.values(cpLayers).forEach(l => map.removeLayer(l));
  segLayers = {}; cpLayers = {};

  activeTrail.segments.forEach(s => {
    const layer = L.geoJSON(s.geojson, { style: { color: DIFF_COLOR[s.difficulty] || '#888', weight: 5 } }).addTo(drawnItems);
    segLayers[s.id] = layer;
  });

  const ordered = [...activeTrail.checkpoints].sort((a, b) => a.order_index - b.order_index);
  ordered.forEach((c, i) => {
    const color = c.show_as_place ? '#278C3E' : '#8FA391';
    const icon = L.divIcon({
      html: `<div style="background:${color};color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.3)">${i + 1}</div>`,
      className: '', iconSize: [24, 24], iconAnchor: [12, 12],
    });
    const m = L.marker([c.lat, c.lon], { icon, draggable: true }).addTo(map);
    m.bindPopup(`<b>${escHtml(c.name)}</b><br><small>${c.show_as_place ? 'показывается как место' : 'только внутри маршрута'}</small>`);
    // Перетащили маркер — сразу сохраняем новые координаты.
    m.on('dragend', async () => {
      const ll = m.getLatLng();
      await api('PATCH', `/checkpoints/${c.id}`, { lat: ll.lat, lon: ll.lng });
      await refreshActiveTrail();
      toast('Координаты обновлены');
    });
    cpLayers[c.id] = m;
  });

  const bounds = drawnItems.getBounds();
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40] });
  else if (ordered.length) map.setView([ordered[0].lat, ordered[0].lon], 14);
}

async function refreshActiveTrail() {
  await loadAll();
  activeTrail = trails.find(t => t.id === activeTrail.id);
  if (!activeTrail) { showTab('routes'); return; }
  drawTrailOnMap();
  renderSegments();
  renderPoints();
}

function startDrawSegment() {
  drawMode = 'segment';
  setHint('Кликайте по карте, чтобы вести тропу. Двойной клик — завершить участок.');
  new L.Draw.Polyline(map, {
    shapeOptions: { color: DIFF_COLOR[document.getElementById('rm-seg-difficulty').value], weight: 5 },
  }).enable();
}

function renderSegments() {
  const el = document.getElementById('rm-segments');
  if (!activeTrail.segments.length) {
    el.innerHTML = `<div class="hint" style="color:var(--muted);font-size:12.5px">Тропа ещё не нарисована.</div>`;
    return;
  }
  el.innerHTML = activeTrail.segments.map((s, i) => `
    <div class="seg">
      <span class="seg-dot ${s.difficulty}"></span>
      <span class="seg-name">Участок ${i + 1}</span>
      <select onchange="changeSegmentDifficulty(${s.id}, this.value)">
        ${optionsHtml(DIFFICULTY_OPTS, s.difficulty)}
      </select>
      <button class="btn btn-danger btn-sm" onclick="deleteSegment(${s.id})">×</button>
    </div>`).join('');
}

async function changeSegmentDifficulty(id, difficulty) {
  await api('PATCH', `/segments/${id}`, { difficulty });
  await refreshActiveTrail();
}

async function deleteSegment(id) {
  if (!confirm('Удалить участок тропы?')) return;
  await api('DELETE', `/segments/${id}`);
  await refreshActiveTrail();
}

// ── Точки маршрута: список, перестановка, вставка ──────────────
function renderPoints() {
  const el = document.getElementById('rm-points');
  const ordered = [...activeTrail.checkpoints].sort((a, b) => a.order_index - b.order_index);
  if (!ordered.length) {
    el.innerHTML = `<div class="hint" style="color:var(--muted);font-size:12.5px">Точек пока нет.</div>`;
    return;
  }
  el.innerHTML = ordered.map((c, i) => `
    <button class="pt-insert" onclick="startAddPoint(${i})">+ Сюда</button>
    <div class="pt" draggable="true" data-id="${c.id}" data-index="${i}">
      <span class="pt-handle">⠿</span>
      <span class="pt-num ${c.show_as_place ? '' : 'hidden-pt'}">${i + 1}</span>
      <div class="pt-main">
        <div class="pt-name">${escHtml(c.name)}</div>
        <div class="pt-meta">${escHtml(categoryLabel(c.category))}</div>
        <label class="toggle" style="margin-top:8px">
          <input type="checkbox" ${c.show_as_place ? 'checked' : ''} onchange="togglePointPublic(${c.id}, this.checked)">
          <span class="toggle-track"></span>
          <span class="toggle-label" style="font-size:12.5px">Выделить отдельной точкой</span>
        </label>
        <div class="pt-actions">
          <button class="btn btn-ghost btn-sm" onclick="openPointForm(${c.id})">Изменить</button>
          <button class="btn btn-ghost btn-sm" onclick="openPhotos('checkpoint', ${c.id})">Фото (${c.photos.length})</button>
          <button class="btn btn-ghost btn-sm" onclick="focusPoint(${c.id})">На карте</button>
          <button class="btn btn-danger btn-sm" onclick="deletePoint(${c.id})">Удалить</button>
        </div>
      </div>
    </div>`).join('') + `<button class="pt-insert" onclick="startAddPoint(${ordered.length})">+ В конец</button>`;

  bindPointDrag();
}

function bindPointDrag() {
  const rows = document.querySelectorAll('#rm-points .pt');
  let draggedId = null;

  rows.forEach(row => {
    row.addEventListener('dragstart', () => {
      draggedId = parseInt(row.dataset.id, 10);
      row.classList.add('dragging');
    });
    row.addEventListener('dragend', () => {
      row.classList.remove('dragging');
      document.querySelectorAll('#rm-points .pt').forEach(r => r.classList.remove('drop-target'));
    });
    row.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (parseInt(row.dataset.id, 10) !== draggedId) row.classList.add('drop-target');
    });
    row.addEventListener('dragleave', () => row.classList.remove('drop-target'));
    row.addEventListener('drop', async (e) => {
      e.preventDefault();
      row.classList.remove('drop-target');
      const targetId = parseInt(row.dataset.id, 10);
      if (!draggedId || draggedId === targetId) return;

      const ordered = [...activeTrail.checkpoints].sort((a, b) => a.order_index - b.order_index).map(c => c.id);
      const from = ordered.indexOf(draggedId);
      const to = ordered.indexOf(targetId);
      ordered.splice(to, 0, ordered.splice(from, 1)[0]);
      await api('PATCH', `/trails/${activeTrail.id}/checkpoints/order`, { ids: ordered });
      await refreshActiveTrail();
    });
  });
}

function startAddPoint(atIndex) {
  drawMode = 'point';
  pendingPointIndex = atIndex;
  setHint(atIndex === null
    ? 'Кликните на карте, чтобы поставить точку в конец маршрута.'
    : `Кликните на карте — точка встанет на позицию ${atIndex + 1}.`);
  new L.Draw.Marker(map).enable();
}

function focusPoint(id) {
  const m = cpLayers[id];
  if (m) { map.setView(m.getLatLng(), 16); m.openPopup(); }
}

async function togglePointPublic(id, checked) {
  await api('PATCH', `/checkpoints/${id}`, { show_as_place: checked });
  await refreshActiveTrail();
  toast(checked ? 'Точка показывается в «Местах»' : 'Точка убрана из «Мест»');
}

async function deletePoint(id) {
  if (!confirm('Удалить точку?')) return;
  await api('DELETE', `/checkpoints/${id}`);
  await refreshActiveTrail();
}

// ── Редактор точки / места ─────────────────────────────────────
// Такая же полноэкранная вкладка, как у статьи, маршрута и сценария: описание
// места — полноценный текст со вставками, и набирать его в модалке на треть
// экрана неудобно.
let editingPlaceId = null;
let placeCreating = null;    // {lat, lon, atIndex, standalone} для новой точки
let placeDraftScope = null;
// Куда вернуться по «Назад» и после сохранения: точку заводят и из списка
// мест, и с карты маршрута — возвращать надо туда, откуда пришли.
let placeReturnView = 'places';

function openPointForm(id, creating) {
  releaseSlots(DESC_EDITOR_SLOTS, 'pl-desc-slot');
  releaseSlots(CRITERIA_SLOTS, 'pl-criteria-slot');
  const c = id ? checkpoints.find(x => x.id === id) : null;
  const v = c || {};
  const inTrail = creating ? !!activeTrail : !!(c && c.trail_id);
  const showAsPlace = c ? c.show_as_place : !inTrail;

  editingPlaceId = c ? c.id : null;
  placeCreating = c ? null : creating;
  placeDraftScope = 'place:' + (c ? c.id : 'new');
  placeReturnView = document.getElementById('view-route-map').classList.contains('active')
    ? 'route-map' : 'places';

  const publishExtra = inTrail ? `
    <label class="toggle" style="margin-top:4px">
      <input type="checkbox" id="m-show-place" ${showAsPlace ? 'checked' : ''}>
      <span class="toggle-track"></span>
      <span class="toggle-label">Выделить отдельной точкой
        <small>Точка получит свою страницу и попадёт в раздел «Места». Без этого она видна только внутри маршрута.</small>
      </span>
    </label>` : '';

  showTab('place-editor');
  document.getElementById('pl-name').value = v.name || '';
  document.getElementById('pl-category').innerHTML = categoryOptionsHtml('checkpoint', v.category_id);
  document.getElementById('pl-duration').value = v.duration_minutes || '';
  document.getElementById('pl-desc-slot').innerHTML = descEditorHtml('Описание');
  document.getElementById('pl-criteria-slot').innerHTML = criteriaHtml(v, { extraPublishHtml: publishExtra });
  document.getElementById('pl-map-hint').style.display = inTrail ? '' : 'none';

  initDescEditor(v.description || '', placeDraftScope);
  autoGrow(document.getElementById('pl-name'));
  setSaveState('', false, 'pl-save-state');
}

function closePlaceEditor() {
  showTab(placeReturnView);
  editingPlaceId = null;
  placeCreating = null;
}

function previewPlace() {
  openPreview(
    'description',
    readDescEditor() || '',
    document.getElementById('pl-name').value.trim(),
    'Место',
  );
}

function schedulePlaceAutosave() {
  if (!document.getElementById('view-place-editor').classList.contains('active')) return;
  setSaveState('Изменения не сохранены', false, 'pl-save-state');
}

async function savePlace() {
  const payload = Object.assign({
    name: document.getElementById('pl-name').value.trim(),
    category_id: parseInt(document.getElementById('pl-category').value, 10) || null,
    duration_minutes: parseInt(document.getElementById('pl-duration').value, 10) || null,
    description: readDescEditor(),
  }, readCriteria());

  const toggleEl = document.getElementById('m-show-place');
  if (toggleEl) payload.show_as_place = toggleEl.checked;

  if (!payload.name) { toast('Введите название', true); return; }

  const creating = placeCreating;
  let saved;
  if (editingPlaceId) {
    saved = await api('PATCH', `/checkpoints/${editingPlaceId}`, payload);
  } else {
    payload.lat = creating.lat;
    payload.lon = creating.lon;
    payload.trail_id = creating.standalone ? null : (activeTrail ? activeTrail.id : null);
    if (creating.standalone) payload.show_as_place = true;
    payload.order_index = activeTrail ? activeTrail.checkpoints.length : 0;
    saved = await api('POST', '/checkpoints', payload);

    // Вставка в середину: создаём в конце, потом двигаем на нужное место.
    if (saved && creating.atIndex !== null && creating.atIndex !== undefined && activeTrail) {
      const ordered = [...activeTrail.checkpoints].sort((a, b) => a.order_index - b.order_index).map(x => x.id);
      ordered.splice(creating.atIndex, 0, saved.id);
      await api('PATCH', `/trails/${activeTrail.id}/checkpoints/order`, { ids: ordered });
    }
  }
  if (!saved) return;

  clearDescDraft(placeDraftScope);
  const wasNew = !editingPlaceId;
  editingPlaceId = saved.id;
  placeCreating = null;
  placeDraftScope = 'place:' + saved.id;
  toast('Сохранено');

  if (activeTrail && placeReturnView === 'route-map') {
    await refreshActiveTrail();
    // Новую точку ставят с карты и обычно ставят следующую — возвращаем туда.
    if (wasNew) { closePlaceEditor(); return; }
  } else {
    await loadAll();
    renderPlaces();
  }
  setSaveState('Сохранено на сервере', true, 'pl-save-state');
}

// ═══════════════════════════════════════════════════════════════
//  МЕСТА
// ═══════════════════════════════════════════════════════════════

function renderPlaces() {
  const q = (document.getElementById('places-search').value || '').toLowerCase();
  const list = checkpoints
    .filter(c => c.show_as_place)
    .filter(c => !q || c.name.toLowerCase().includes(q));
  const el = document.getElementById('places-list');
  if (!list.length) {
    el.innerHTML = `<div class="empty"><b>Мест нет</b>Добавьте отдельное место или выделите точку внутри маршрута.</div>`;
    return;
  }
  el.innerHTML = list.map(c => {
    const cover = (c.photos && c.photos.length) ? c.photos[0].thumb_url || c.photos[0].url : '';
    const trail = c.trail_id ? trails.find(t => t.id === c.trail_id) : null;
    return `
    <div class="row">
      <div class="row-thumb" style="${cover ? `background-image:url('${escAttr(cover)}')` : ''}"></div>
      <div class="row-main">
        <div class="row-title">${escHtml(c.name)}
          ${c.popularity === 'top' ? '<span class="badge badge-gold">Топ</span>' : ''}
          ${trail ? `<span class="badge">в маршруте «${escHtml(trail.name)}»</span>` : ''}
        </div>
        <div class="row-meta">
          <span>${escHtml(categoryLabel(c.category))}</span>
          ${c.district ? `<span>${escHtml((DISTRICT_OPTS.find(d => d.code === c.district) || {}).label || c.district)}</span>` : ''}
          ${c.is_paid ? '<span>платно</span>' : ''}
        </div>
      </div>
      <div class="row-actions">
        <a class="btn btn-ghost btn-sm" href="/mesta/${c.id}" target="_blank" rel="noopener">Открыть</a>
        <button class="btn btn-ghost btn-sm" onclick="openPointForm(${c.id})">Редактировать</button>
        <button class="btn btn-ghost btn-sm" onclick="openPhotos('checkpoint', ${c.id})">Фото (${c.photos.length})</button>
        <button class="btn btn-danger btn-sm" onclick="deletePlace(${c.id})">Удалить</button>
      </div>
    </div>`;
  }).join('');
}

async function deletePlace(id) {
  if (!confirm('Удалить место?')) return;
  await api('DELETE', `/checkpoints/${id}`);
  await loadAll();
}

function startAddStandalonePlace() {
  showTab('place-map');
  ensurePlaceMap();
  placePickCallback = (lat, lon) => {
    showTab('places');
    openPointForm(null, { lat, lon, standalone: true, atIndex: null });
  };
}

function cancelPlacePicking() {
  placePickCallback = null;
  showTab('places');
}

function ensurePlaceMap() {
  if (!placeMap) {
    placeMap = L.map('place-map').setView([44.15, 40.17], 11);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap', maxZoom: 18,
    }).addTo(placeMap);
    placeMap.on('click', (e) => {
      if (placePickCallback) {
        const cb = placePickCallback;
        placePickCallback = null;
        cb(e.latlng.lat, e.latlng.lng);
      }
    });
  }
  setTimeout(() => placeMap.invalidateSize(), 60);
}

// ═══════════════════════════════════════════════════════════════
//  ФОТО ОБЪЕКТА
// ═══════════════════════════════════════════════════════════════

function openPhotos(kind, id) {
  const obj = kind === 'trail' ? trails.find(t => t.id === id) : checkpoints.find(c => c.id === id);
  if (!obj) return;
  const photos = obj.photos || [];
  showModal(`Фото — ${obj.name}`, `
    <div class="hint" style="color:var(--muted);font-size:13px;margin-bottom:14px">
      Первое фото становится обложкой на карточке и в соцсетях.
    </div>
    <div class="photos" id="photo-grid">
      ${photos.map(p => `
        <div class="photo">
          <img src="${escAttr(p.thumb_url || p.url)}" alt="">
          <button onclick="deletePhoto(${p.id}, '${kind}', ${id})">×</button>
        </div>`).join('') || '<div class="picker-empty">Фото пока нет</div>'}
    </div>
    <div class="field" style="margin-top:16px;margin-bottom:0">
      <label>Добавить фото</label>
      <input type="file" id="ph-file" accept="image/jpeg,image/png,image/webp" multiple>
    </div>
  `, async () => {
    const input = document.getElementById('ph-file');
    if (!input.files.length) { closeModal(); return; }
    document.getElementById('modal-save').disabled = true;
    document.getElementById('modal-save').textContent = 'Загружаю...';
    for (const file of Array.from(input.files)) {
      const up = await uploadFile(file);
      if (up) {
        const path = kind === 'trail' ? `/trails/${id}/photos` : `/checkpoints/${id}/photos`;
        await api('POST', path, { url: up.url, thumb_url: up.thumb_url });
      }
    }
    document.getElementById('modal-save').disabled = false;
    await loadAll();
    closeModal();
    toast('Фото добавлены');
    if (activeTrail && document.getElementById('view-route-map').classList.contains('active')) refreshActiveTrail();
    renderPlaces(); renderRoutes();
  }, { saveLabel: 'Загрузить' });
}

async function deletePhoto(photoId, kind, ownerId) {
  if (!confirm('Удалить фото?')) return;
  await api('DELETE', `/photos/${photoId}`);
  await loadAll();
  openPhotos(kind, ownerId);
  renderPlaces(); renderRoutes();
}

// ═══════════════════════════════════════════════════════════════
//  СЦЕНАРИИ — двери развилки на главной. Места и маршруты внутри не
//  перечисляются: сайт сам подбирает их по filter_*-правилу на каждый рендер.
// ═══════════════════════════════════════════════════════════════

const ICON_CHOICES = [
  '🧭','👶','🚌','❄️','🥾','⛰️','💧','🏔️','🚗','🎒','☀️','🌧️',
  '🏕️','📸','💰','⏱️','🗺️','🧳','🌲','🏞️','⛺','🌊','🐾','🎣',
];

function renderScenarios() {
  const el = document.getElementById('scenarios-list');
  if (!scenarios.length) {
    el.innerHTML = `<div class="empty"><b>Сценариев нет</b>Создайте первую дверь развилки — например, «Еду с детьми».</div>`;
    return;
  }
  const sorted = [...scenarios].sort((a, b) => a.order_index - b.order_index);
  el.innerHTML = sorted.map(s => {
    const filters = [];
    if (s.filter_kid_friendly !== 'any') filters.push(s.filter_kid_friendly === 'yes' ? 'с детьми' : 'не для детей');
    if (s.filter_seasonality !== 'any') filters.push(s.filter_seasonality === 'year_round' ? 'круглый год' : 'только летом');
    if (s.filter_popularity.length) filters.push('популярность: ' + s.filter_popularity.join(', '));
    if (s.filter_difficulty.length) filters.push('сложность: ' + s.filter_difficulty.join(', '));
    if (s.filter_access.length) filters.push('доступ: ' + s.filter_access.join(', '));
    return `
    <div class="row">
      <div class="row-thumb" style="display:flex;align-items:center;justify-content:center;font-size:24px;background:var(--accent-soft)">${s.icon || '🧭'}</div>
      <div class="row-main">
        <div class="row-title">${escHtml(s.door)}
          ${s.is_published ? '' : '<span class="badge badge-draft">скрыт</span>'}
        </div>
        <div class="row-meta">
          <span>/kuda/${escHtml(s.slug)}</span>
          ${filters.length ? `<span>${escHtml(filters.join(' · '))}</span>` : '<span>без ограничений — берёт всё</span>'}
        </div>
      </div>
      <div class="row-actions">
        <a class="btn btn-ghost btn-sm" href="/kuda/${escAttr(s.slug)}" target="_blank" rel="noopener">Открыть</a>
        <button class="btn btn-ghost btn-sm" onclick="openScenarioForm(${s.id})">Редактировать</button>
        <button class="btn btn-danger btn-sm" onclick="deleteScenario(${s.id})">Удалить</button>
      </div>
    </div>`;
  }).join('');
}

function iconPickerHtml(selected) {
  const chips = ICON_CHOICES.map(e =>
    `<button type="button" class="icon-chip ${e === selected ? 'active' : ''}" data-icon="${e}" onclick="pickScenarioIcon(this)">${e}</button>`
  ).join('');
  return `<div class="icon-picker">
    <div class="icon-grid">${chips}</div>
    <input type="text" id="sc-icon" value="${escAttr(selected || '')}" maxlength="4" placeholder="или впишите свой эмодзи" oninput="syncScenarioIconInput()">
  </div>`;
}

function pickScenarioIcon(btn) {
  document.querySelectorAll('.icon-chip').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('sc-icon').value = btn.dataset.icon;
}

function syncScenarioIconInput() {
  const val = document.getElementById('sc-icon').value.trim();
  document.querySelectorAll('.icon-chip').forEach(b => b.classList.toggle('active', b.dataset.icon === val));
}

function tipRowHtml(text) {
  return `<div class="tip-row">
    <input class="tip-input" value="${escAttr(text || '')}" placeholder="Например: возьмите наличные — карты принимают не везде">
    <button type="button" class="btn btn-danger btn-sm" onclick="this.closest('.tip-row').remove()">×</button>
  </div>`;
}

function multiChipsHtml(cssClass, opts, selected) {
  selected = selected || [];
  return `<div class="chips">${opts.map(o =>
    `<label class="chip"><input type="checkbox" class="${cssClass}" value="${o.code}" ${selected.includes(o.code) ? 'checked' : ''}><span>${escHtml(o.label)}</span></label>`
  ).join('')}</div>`;
}

function readMultiChips(cssClass) {
  return Array.from(document.querySelectorAll(`.${cssClass}:checked`)).map(el => el.value);
}

let editingScenarioId = null;

function openScenarioForm(id) {
  releaseSlots(DESC_EDITOR_SLOTS, 'sc-desc-slot');
  editingScenarioId = id;
  showTab('scenario-editor');

  const s = id ? scenarios.find(x => x.id === id) : null;
  const v = s || { icon: '🧭', filter_kid_friendly: 'any', filter_seasonality: 'any', filter_popularity: [], filter_difficulty: [], filter_access: [], is_published: true, order_index: scenarios.length };

  document.getElementById('sc-icon-picker').innerHTML = iconPickerHtml(v.icon);
  document.getElementById('sc-door').value = v.door || '';
  document.getElementById('sc-hint').value = v.hint || '';
  document.getElementById('sc-title').value = v.title || '';
  document.getElementById('sc-slug').value = v.slug || '';
  document.getElementById('sc-cover-url').value = v.cover_url || '';
  document.getElementById('sc-cover-file').value = '';
  document.getElementById('sc-tile-cover-url').value = v.tile_cover_url || '';
  document.getElementById('sc-tile-cover-file').value = '';
  document.getElementById('sc-seo').value = v.seo_description || '';
  document.getElementById('sc-order').value = v.order_index;
  document.getElementById('sc-published').checked = v.is_published !== false;

  document.getElementById('sc-kid').innerHTML = `
    <option value="any" ${v.filter_kid_friendly === 'any' ? 'selected' : ''}>Неважно</option>
    <option value="yes" ${v.filter_kid_friendly === 'yes' ? 'selected' : ''}>Подходит с детьми</option>
    <option value="no" ${v.filter_kid_friendly === 'no' ? 'selected' : ''}>Не для детей</option>`;
  document.getElementById('sc-season').innerHTML = `
    <option value="any" ${v.filter_seasonality === 'any' ? 'selected' : ''}>Неважно</option>
    <option value="year_round" ${v.filter_seasonality === 'year_round' ? 'selected' : ''}>Круглый год</option>
    <option value="summer_only" ${v.filter_seasonality === 'summer_only' ? 'selected' : ''}>Только летом</option>`;
  document.getElementById('sc-pop-chips').innerHTML = multiChipsHtml('sc-pop-check', POPULARITY_OPTS, v.filter_popularity);
  document.getElementById('sc-diff-chips').innerHTML = multiChipsHtml('sc-diff-check', DIFFICULTY_OPTS, v.filter_difficulty);
  document.getElementById('sc-acc-chips').innerHTML = multiChipsHtml('sc-acc-check', ACCESS_OPTS, v.filter_access);

  document.getElementById('sc-articles').innerHTML = pickerHtml(articles, v.featured_article_ids || [], a => a.title);
  document.getElementById('sc-desc-slot').innerHTML = descEditorHtml('Вступительный текст');

  setupCoverPreview('sc-cover-file', 'sc-cover-url', 'sc-cover-preview');
  setupCoverPreview('sc-tile-cover-file', 'sc-tile-cover-url', 'sc-tile-cover-preview');
  initDescEditor(v.lead || '', 'scenario:' + (s ? s.id : 'new'));
  autoGrow(document.getElementById('sc-title'));
  setSaveState('', false, 'sc-save-state');
}

function closeScenarioEditor() {
  showTab('scenarios');
  editingScenarioId = null;
}

function previewScenario() {
  openPreview(
    'description',
    readDescEditor() || '',
    document.getElementById('sc-title').value.trim(),
    'Сценарий',
  );
}

async function saveScenario() {
  const door = document.getElementById('sc-door').value.trim();
  const title = document.getElementById('sc-title').value.trim();
  if (!door || !title) { toast('Заполните подпись и заголовок', true); return; }

  let coverUrl = document.getElementById('sc-cover-url').value.trim();
  let coverThumb = null;
  const coverFileEl = document.getElementById('sc-cover-file');
  if (coverFileEl.files.length) {
    const up = await uploadFile(coverFileEl.files[0]);
    if (up) { coverUrl = up.url; coverThumb = up.thumb_url; }
  }

  let tileCoverUrl = document.getElementById('sc-tile-cover-url').value.trim();
  let tileCoverThumb = null;
  const tileCoverFileEl = document.getElementById('sc-tile-cover-file');
  if (tileCoverFileEl.files.length) {
    const up = await uploadFile(tileCoverFileEl.files[0]);
    if (up) { tileCoverUrl = up.url; tileCoverThumb = up.thumb_url; }
  }

  const payload = {
    icon: document.getElementById('sc-icon').value.trim() || null,
    door,
    hint: document.getElementById('sc-hint').value.trim() || null,
    title,
    slug: document.getElementById('sc-slug').value.trim() || null,
    lead: readDescEditor(),
    cover_url: coverUrl || null,
    cover_thumb_url: coverUrl ? coverThumb : null,
    tile_cover_url: tileCoverUrl || null,
    tile_cover_thumb_url: tileCoverUrl ? tileCoverThumb : null,
    seo_description: document.getElementById('sc-seo').value.trim() || null,
    featured_article_ids: readPicker('sc-articles'),
    filter_kid_friendly: document.getElementById('sc-kid').value,
    filter_seasonality: document.getElementById('sc-season').value,
    filter_popularity: readMultiChips('sc-pop-check'),
    filter_difficulty: readMultiChips('sc-diff-check'),
    filter_access: readMultiChips('sc-acc-check'),
    order_index: parseInt(document.getElementById('sc-order').value, 10) || 0,
    is_published: document.getElementById('sc-published').checked,
  };

  const saved = editingScenarioId
    ? await api('PATCH', `/scenarios/${editingScenarioId}`, payload)
    : await api('POST', '/scenarios', payload);
  if (!saved) return;

  clearDescDraft('scenario:' + (editingScenarioId || 'new'));
  editingScenarioId = saved.id;
  await loadAll();
  setSaveState('Сохранено на сервере', true, 'sc-save-state');
  toast('Сценарий сохранён');
}

function scheduleScenarioAutosave() {
  if (!document.getElementById('view-scenario-editor').classList.contains('active')) return;
  setSaveState('Изменения не сохранены', false, 'sc-save-state');
}

async function deleteScenario(id) {
  if (!confirm('Удалить сценарий? Дверь пропадёт с развилки на главной.')) return;
  await api('DELETE', `/scenarios/${id}`);
  await loadAll();
}

// ═══════════════════════════════════════════════════════════════
//  БЛОКИ ДЛЯ СТАТЕЙ — лид-магниты и наборы вопросов
//
//  В теле статьи сохраняется только пустой <div> со ссылкой на id, а
//  содержимое подставляет сервер на рендере — поэтому правка блока
//  обновляет все статьи, где он вставлен. Внутри редактора в этот div
//  рисуется превью, но оно вычищается при сохранении (readArticleBody),
//  чтобы в базу не попала копия текста.
// ═══════════════════════════════════════════════════════════════

function registerEmbedBlots() {
  if (window.__embedBlotsRegistered) return;
  const BlockEmbed = Quill.import('blots/block/embed');

  class MagnetBlot extends BlockEmbed {
    static create(value) {
      const node = super.create();
      node.setAttribute('data-magnet-id', value.id);
      node.setAttribute('contenteditable', 'false');
      const m = magnets.find(x => String(x.id) === String(value.id));
      node.innerHTML = '<span class="embed-tag">Лид-магнит</span><b>' +
        escHtml(m ? m.title : 'блок удалён') + '</b>';
      return node;
    }
    static value(node) { return { id: node.getAttribute('data-magnet-id') }; }
  }
  MagnetBlot.blotName = 'magnet';
  MagnetBlot.tagName = 'div';
  MagnetBlot.className = 'magnet-embed';

  class FaqBlot extends BlockEmbed {
    static create(value) {
      const node = super.create();
      node.setAttribute('data-faq-id', value.id);
      node.setAttribute('contenteditable', 'false');
      const f = faqSets.find(x => String(x.id) === String(value.id));
      const cnt = f ? (f.items || []).length : 0;
      node.innerHTML = '<span class="embed-tag">Вопросы</span><b>' +
        escHtml(f ? f.name : 'набор удалён') + '</b>' +
        (f ? '<span class="embed-meta">' + cnt + ' вопр.</span>' : '');
      return node;
    }
    static value(node) { return { id: node.getAttribute('data-faq-id') }; }
  }
  FaqBlot.blotName = 'faqset';
  FaqBlot.tagName = 'div';
  FaqBlot.className = 'faq-embed';

  // «Что учесть» — в отличие от магнита и набора вопросов, не отдельная
  // таблица: список советов лежит прямо в data-tips вставки, поэтому блок
  // доступен в любом редакторе (статья, описание маршрута/места, сценарий),
  // а не только там, где заведён специальный справочник.
  class ConsiderBlot extends BlockEmbed {
    static create(value) {
      const node = super.create();
      const tips = (value && value.tips) || [];
      node.setAttribute('data-tips', JSON.stringify(tips));
      node.setAttribute('contenteditable', 'false');
      node.innerHTML = '<span class="embed-tag">Что учесть</span><ul>' +
        tips.map(t => '<li>' + escHtml(t) + '</li>').join('') + '</ul>';
      return node;
    }
    static value(node) {
      try { return { tips: JSON.parse(node.getAttribute('data-tips') || '[]') }; }
      catch (e) { return { tips: [] }; }
    }
  }
  ConsiderBlot.blotName = 'consider';
  ConsiderBlot.tagName = 'div';
  ConsiderBlot.className = 'consider-embed';

  Quill.register(MagnetBlot);
  Quill.register(FaqBlot);
  Quill.register(ConsiderBlot);
  window.__embedBlotsRegistered = true;
}

// ── «Что учесть» — локальный блок: вставка и правка через второе,
// стековое модальное окно (обычное занято формой маршрута/места/сценария) ──
function addTipRowIn(containerId) {
  document.getElementById(containerId).insertAdjacentHTML('beforeend', tipRowHtml(''));
}

function readTipRowsIn(containerId) {
  return Array.from(document.querySelectorAll('#' + containerId + ' .tip-input')).map(el => el.value.trim()).filter(Boolean);
}

function openConsiderEditor(quill, node) {
  const existing = node ? (JSON.parse(node.getAttribute('data-tips') || '[]')) : [];
  showModal2('Что учесть', `
    <div class="field">
      <div class="hint" style="margin:0 0 8px">Короткие советы — покажутся отдельным блоком прямо в этом месте текста.</div>
      <div id="cb-tips">${(existing.length ? existing : ['']).map(tipRowHtml).join('')}</div>
      <button type="button" class="btn btn-ghost btn-sm" onclick="addTipRowIn('cb-tips')">+ Совет</button>
    </div>
  `, async () => {
    const tips = readTipRowsIn('cb-tips');
    if (!tips.length) { toast('Добавьте хотя бы один совет', true); return; }
    if (node) {
      const idx = quill.getIndex(Quill.find(node));
      quill.deleteText(idx, 1, 'user');
      quill.insertEmbed(idx, 'consider', { tips }, 'user');
      quill.setSelection(idx + 1);
    } else {
      const range = quill.getSelection(true);
      const at = range ? range.index : quill.getLength() - 1;
      quill.insertEmbed(at, 'consider', { tips }, 'user');
      quill.setSelection(at + 1);
    }
    closeModal2();
  }, { saveLabel: node ? 'Сохранить' : 'Вставить' });
}

function insertConsiderBlock(quill) {
  if (!quill) return;
  openConsiderEditor(quill, null);
}

document.addEventListener('click', (e) => {
  const embed = e.target.closest('.consider-embed');
  if (!embed) return;
  const quill = embed.closest('#article-editor') ? articleQuill : descQuill;
  openConsiderEditor(quill, embed);
});

function insertMagnet(quill) {
  quill = quill || articleQuill;
  if (!magnets.length) { toast('Сначала создайте лид-магнит во вкладке «Блоки»', true); return; }
  // Позицию курсора запоминаем ДО открытия диалога выбора — так же, как в
  // photoFlow/insertInternalLink. Иначе к моменту клика по варианту в модалке
  // редактор уже потерял фокус, getSelection() отдаёт null, и вставка вместо
  // места курсора уезжает в конец текста.
  const at = currentInsertIndex(quill);
  pickEmbed('Вставить лид-магнит', magnets, m => m.name + ' — ' + m.title, (id) => {
    quill.insertEmbed(at, 'magnet', { id: id }, 'user');
    quill.setSelection(at + 1);
    scheduleAutosave();
  });
}

function insertFaqSet(quill) {
  quill = quill || articleQuill;
  if (!faqSets.length) { toast('Сначала создайте набор вопросов во вкладке «Блоки»', true); return; }
  const at = currentInsertIndex(quill);
  pickEmbed('Вставить набор вопросов', faqSets, f => f.name + ' (' + (f.items || []).length + ' вопр.)', (id) => {
    quill.insertEmbed(at, 'faqset', { id: id }, 'user');
    quill.setSelection(at + 1);
    scheduleAutosave();
  });
}

function pickEmbed(title, items, labelFn, onPick) {
  const rows = items.map(it =>
    '<label class="picker-item"><input type="radio" name="embed-target" value="' + it.id + '">' +
    '<span>' + escHtml(labelFn(it)) + '</span></label>').join('');
  showModal2(title,
    '<div class="picker"><input type="text" class="picker-search" placeholder="Поиск..." oninput="filterPicker(this)">' +
    '<div class="picker-list">' + rows + '</div></div>',
    () => {
      const picked = document.querySelector('input[name=embed-target]:checked');
      if (!picked) { toast('Выберите блок', true); return; }
      onPick(parseInt(picked.value, 10));
      closeModal2();
    }, { saveLabel: 'Вставить' });
}

// ── Списки блоков ──────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════
//  СТРАНИЦЫ САЙТА — шапка главной и страница клуба. Обе строки всегда
//  существуют (засеяны на старте), поэтому здесь только редактирование.
// ═══════════════════════════════════════════════════════════════

const SITE_PAGE_LABELS = { home: 'Главная страница', club: 'Страница клуба' };

function renderSitePages() {
  const el = document.getElementById('site-pages-list');
  if (!el) return;
  el.innerHTML = sitePages.map(p => `
    <div class="row">
      <div class="row-main">
        <div class="row-title">${escHtml(SITE_PAGE_LABELS[p.slug] || p.slug)}</div>
        <div class="row-meta"><span>${escHtml(p.title || '')}</span></div>
      </div>
      <div class="row-actions">
        <button class="btn btn-ghost btn-sm" onclick="openSitePageForm('${p.slug}')">Редактировать</button>
      </div>
    </div>`).join('');
}

function openSitePageForm(slug) {
  const p = sitePages.find(x => x.slug === slug) || {};
  const hasButton = slug === 'club';
  showModal(SITE_PAGE_LABELS[slug] || slug, `
    <div class="field"><label>Надпись над заголовком</label>
      <input id="sp-eyebrow" value="${escAttr(p.eyebrow || '')}" placeholder="Привет">
    </div>
    <div class="field"><label>Заголовок</label>
      <input id="sp-title" value="${escAttr(p.title || '')}">
    </div>
    <div class="field"><label>Текст под заголовком</label>
      <textarea id="sp-lead">${escHtml(p.lead || '')}</textarea>
    </div>
    <div class="field"><label>${slug === 'club' ? 'Второй абзац' : 'Подпись у карточки-подборки справа'}</label>
      <textarea id="sp-lead-extra">${escHtml(p.lead_extra || '')}</textarea>
    </div>
    ${hasButton ? `<div class="field" style="margin-bottom:0"><label>Текст на кнопке</label>
      <input id="sp-button" value="${escAttr(p.button_text || '')}">
    </div>` : ''}
  `, async () => {
    const payload = {
      eyebrow: document.getElementById('sp-eyebrow').value.trim() || null,
      title: document.getElementById('sp-title').value.trim() || null,
      lead: document.getElementById('sp-lead').value.trim() || null,
      lead_extra: document.getElementById('sp-lead-extra').value.trim() || null,
      button_text: hasButton ? (document.getElementById('sp-button').value.trim() || null) : (p.button_text || null),
    };
    const saved = await api('PATCH', `/site-pages/${slug}`, payload);
    if (saved) { await loadAll(); closeModal(); toast('Сохранено'); }
  }, { wide: true });
}

function renderBlocks() {
  const mEl = document.getElementById('magnets-list');
  if (mEl) {
    mEl.innerHTML = magnets.length ? magnets.map(m => {
      const noLinks = !m.telegram_url && !m.max_url;
      return '<div class="row">' +
        '<div class="row-thumb block-icon">🎁</div>' +
        '<div class="row-main"><div class="row-title">' + escHtml(m.name) +
        (m.is_published ? '' : '<span class="badge badge-draft">скрыт</span>') +
        (noLinks ? '<span class="badge badge-draft">нет ссылок — на сайте не показывается</span>' : '') +
        '</div><div class="row-meta"><span>' + escHtml(m.title) + '</span></div></div>' +
        '<div class="row-actions">' +
        '<button class="btn btn-ghost btn-sm" onclick="openMagnetForm(' + m.id + ')">Редактировать</button>' +
        '<button class="btn btn-danger btn-sm" onclick="deleteMagnet(' + m.id + ')">Удалить</button>' +
        '</div></div>';
    }).join('') : '<div class="empty"><b>Магнитов нет</b>Создайте блок с приманкой и кнопкой в клуб.</div>';
  }

  const fEl = document.getElementById('faqsets-list');
  if (fEl) {
    fEl.innerHTML = faqSets.length ? faqSets.map(f =>
      '<div class="row">' +
      '<div class="row-thumb block-icon">❓</div>' +
      '<div class="row-main"><div class="row-title">' + escHtml(f.name) +
      (f.is_published ? '' : '<span class="badge badge-draft">скрыт</span>') +
      (f.on_faq_page ? '<span class="badge badge-green">на странице «Вопросы»</span>' : '') +
      '</div><div class="row-meta"><span>' + (f.items || []).length + ' вопросов</span></div></div>' +
      '<div class="row-actions">' +
      '<button class="btn btn-ghost btn-sm" onclick="openFaqSetForm(' + f.id + ')">Редактировать</button>' +
      '<button class="btn btn-danger btn-sm" onclick="deleteFaqSet(' + f.id + ')">Удалить</button>' +
      '</div></div>').join('') : '<div class="empty"><b>Наборов нет</b>Сгруппируйте частые вопросы, чтобы вставлять их в статьи.</div>';
  }
}

// ── Лид-магнит: форма с живым предпросмотром ───────────────────
function openMagnetForm(id) {
  const m = id ? magnets.find(x => x.id === id) : null;
  const v = m || { button_text: 'Забрать в клубе', is_published: true };
  showModal(m ? 'Лид-магнит: ' + m.name : 'Новый лид-магнит',
    '<div class="field"><label>Название (только для этого списка)</label>' +
    '<input id="mg-name" value="' + escAttr(v.name || '') + '" placeholder="Чек-лист снаряжения" oninput="renderMagnetPreview()"></div>' +

    '<div class="field"><label>Заголовок-приманка</label>' +
    '<input id="mg-title" value="' + escAttr(v.title || '') + '" placeholder="Забыть что-то в горах обиднее, чем взять лишнее" oninput="renderMagnetPreview()"></div>' +

    '<div class="field"><label>Пояснение</label>' +
    '<textarea id="mg-text" placeholder="Что именно человек получит и где это лежит" oninput="renderMagnetPreview()">' + escHtml(v.text || '') + '</textarea></div>' +

    '<div class="field-row">' +
    '<div class="field"><label>Текст на кнопке</label>' +
    '<input id="mg-btn" value="' + escAttr(v.button_text || '') + '" oninput="renderMagnetPreview()"></div>' +
    '<div class="field"><label>Подпись под кнопкой</label>' +
    '<input id="mg-note" value="' + escAttr(v.note || '') + '" placeholder="Без регистрации" oninput="renderMagnetPreview()"></div>' +
    '</div>' +

    '<div class="field"><label>Ссылка в Telegram</label>' +
    '<input id="mg-tg" value="' + escAttr(v.telegram_url || '') + '" placeholder="https://t.me/..." oninput="renderMagnetPreview()"></div>' +

    '<div class="field"><label>Ссылка в MAX</label>' +
    '<input id="mg-max" value="' + escAttr(v.max_url || '') + '" placeholder="https://max.ru/..." oninput="renderMagnetPreview()">' +
    '<div class="hint">Можно заполнить только одну — тогда выбор мессенджера читателю не показывается. Если не заполнить ни одной, блок на сайте не появится.</div></div>' +

    '<label class="toggle" style="margin-bottom:14px"><input type="checkbox" id="mg-published" ' +
    (v.is_published !== false ? 'checked' : '') + '><span class="toggle-track"></span>' +
    '<span class="toggle-label">Показывать на сайте</span></label>' +

    '<div class="field" style="margin-bottom:0"><label>Как это увидит читатель</label>' +
    '<div class="block-preview" id="mg-preview"></div></div>',
  async () => {
    const payload = {
      name: document.getElementById('mg-name').value.trim(),
      title: document.getElementById('mg-title').value.trim(),
      text: document.getElementById('mg-text').value.trim() || null,
      button_text: document.getElementById('mg-btn').value.trim() || 'Забрать в клубе',
      note: document.getElementById('mg-note').value.trim() || null,
      telegram_url: document.getElementById('mg-tg').value.trim() || null,
      max_url: document.getElementById('mg-max').value.trim() || null,
      is_published: document.getElementById('mg-published').checked,
    };
    if (!payload.name || !payload.title) { toast('Заполните название и заголовок', true); return; }
    const saved = m ? await api('PATCH', '/magnets/' + m.id, payload) : await api('POST', '/magnets', payload);
    if (saved) { await loadAll(); closeModal(); toast('Магнит сохранён'); }
  }, { wide: true });
  renderMagnetPreview();
}

function renderMagnetPreview() {
  const el = document.getElementById('mg-preview');
  if (!el) return;
  const title = document.getElementById('mg-title').value.trim();
  const text = document.getElementById('mg-text').value.trim();
  const note = document.getElementById('mg-note').value.trim();
  const tg = document.getElementById('mg-tg').value.trim();
  const max = document.getElementById('mg-max').value.trim();

  if (!tg && !max) {
    el.innerHTML = '<div class="preview-warn">Ни одной ссылки не задано — на сайте блок показан не будет.</div>';
    return;
  }
  const pills =
    (tg ? '<span class="pv-pill pv-pill-tg"><img src="/assets/magnet-tg.png?v=' + ADMIN_ASSET_BUST + '" alt=""><span>Telegram</span></span>' : '') +
    (max ? '<span class="pv-pill pv-pill-max"><img src="/assets/magnet-max.png?v=' + ADMIN_ASSET_BUST + '" alt=""><span>MAX</span></span>' : '');

  el.innerHTML =
    '<div class="pv-magnet">' +
      '<div class="pv-top"><img class="pv-gift" src="/assets/magnet-gift.png?v=' + ADMIN_ASSET_BUST + '" alt=""><div>' +
        '<p class="pv-title">' + escHtml(title || 'Заголовок-приманка') + '</p>' +
        (text ? '<p class="pv-text">' + escHtml(text) + '</p>' : '') +
      '</div></div>' +
      '<div class="pv-cta"><div class="pv-cta-copy"><span class="pv-kicker">Забирайте</span><span class="pv-btn">Бесплатно</span>' +
        (note ? '<p class="pv-note">' + escHtml(note) + '</p>' : '') +
      '</div><div class="pv-actions">' + pills + '</div></div>' +
    '</div>';
}

async function deleteMagnet(id) {
  if (!confirm('Удалить магнит? Из статей, где он вставлен, блок пропадёт.')) return;
  await api('DELETE', '/magnets/' + id);
  await loadAll();
}

// ── Набор вопросов: форма с предпросмотром-аккордеоном ─────────
function openFaqSetForm(id) {
  const f = id ? faqSets.find(x => x.id === id) : null;
  const v = f || { items: [], is_published: true, on_faq_page: false, order_index: faqSets.length };
  showModal(f ? 'Набор: ' + f.name : 'Новый набор вопросов',
    '<div class="field-row">' +
    '<div class="field"><label>Название набора</label>' +
    '<input id="fs-name" value="' + escAttr(v.name || '') + '" placeholder="Общие вопросы"></div>' +
    '<div class="field"><label>Заголовок над блоком</label>' +
    '<input id="fs-title" value="' + escAttr(v.title || '') + '" placeholder="Частые вопросы"></div>' +
    '</div>' +

    '<div class="field"><label>Вопросы</label>' +
    '<div class="hint" style="margin:0 0 8px">Перетаскивайте за ⠿, чтобы менять порядок.</div>' +
    '<div id="fs-items">' + (v.items || []).map(faqItemRowHtml).join('') + '</div>' +
    '<button type="button" class="btn btn-ghost btn-sm" onclick="addFaqItemRow()">+ Вопрос</button></div>' +

    '<div class="field-row">' +
    '<div class="field"><label>Порядок на странице «Вопросы»</label>' +
    '<input id="fs-order" type="number" value="' + (v.order_index || 0) + '"></div>' +
    '<div class="field" style="padding-top:22px">' +
    '<label class="toggle" style="margin-bottom:8px"><input type="checkbox" id="fs-onpage" ' +
    (v.on_faq_page ? 'checked' : '') + '><span class="toggle-track"></span>' +
    '<span class="toggle-label">Показывать на /voprosy</span></label>' +
    '<label class="toggle"><input type="checkbox" id="fs-published" ' +
    (v.is_published !== false ? 'checked' : '') + '><span class="toggle-track"></span>' +
    '<span class="toggle-label">Показывать на сайте</span></label>' +
    '</div></div>' +

    '<div class="field" style="margin-bottom:0"><label>Как это увидит читатель</label>' +
    '<div class="block-preview" id="fs-preview"></div></div>',
  async () => {
    const payload = {
      name: document.getElementById('fs-name').value.trim(),
      title: document.getElementById('fs-title').value.trim() || null,
      items: readFaqItemRows(),
      on_faq_page: document.getElementById('fs-onpage').checked,
      order_index: parseInt(document.getElementById('fs-order').value, 10) || 0,
      is_published: document.getElementById('fs-published').checked,
    };
    if (!payload.name) { toast('Введите название набора', true); return; }
    if (!payload.items.length) { toast('Добавьте хотя бы один вопрос', true); return; }
    const saved = f ? await api('PATCH', '/faq-sets/' + f.id, payload) : await api('POST', '/faq-sets', payload);
    if (saved) { await loadAll(); closeModal(); toast('Набор сохранён'); }
  }, { wide: true });
  bindFaqItemDrag();
  renderFaqSetPreview();
}

function faqItemRowHtml(item) {
  item = item || { question: '', answer: '' };
  return '<div class="faq-item-row" draggable="true">' +
    '<span class="pt-handle">⠿</span><div style="flex:1">' +
    '<div class="field" style="margin-bottom:6px"><input class="fi-q" placeholder="Вопрос" value="' +
    escAttr(item.question) + '" oninput="renderFaqSetPreview()"></div>' +
    '<div class="field" style="margin-bottom:0"><textarea class="fi-a" placeholder="Ответ" oninput="renderFaqSetPreview()">' +
    escHtml(item.answer || '') + '</textarea></div></div>' +
    '<button type="button" class="btn btn-danger btn-sm" onclick="this.closest(\'.faq-item-row\').remove(); renderFaqSetPreview()">×</button></div>';
}

function addFaqItemRow() {
  document.getElementById('fs-items').insertAdjacentHTML('beforeend', faqItemRowHtml());
  bindFaqItemDrag();
  renderFaqSetPreview();
}

function readFaqItemRows() {
  return Array.from(document.querySelectorAll('#fs-items .faq-item-row')).map(row => ({
    question: row.querySelector('.fi-q').value.trim(),
    answer: row.querySelector('.fi-a').value.trim(),
  })).filter(i => i.question && i.answer);
}

function renderFaqSetPreview() {
  const el = document.getElementById('fs-preview');
  if (!el) return;
  const items = readFaqItemRows();
  if (!items.length) { el.innerHTML = '<div class="preview-warn">Добавьте хотя бы один вопрос.</div>'; return; }
  const title = document.getElementById('fs-title').value.trim() || 'Частые вопросы';
  el.innerHTML = '<div class="pv-faq"><h4>' + escHtml(title) + '</h4>' +
    items.map(i => '<details class="pv-faq-item"><summary>' + escHtml(i.question) + '</summary>' +
      '<p>' + escHtml(i.answer) + '</p></details>').join('') + '</div>';
}

function bindFaqItemDrag() {
  let dragged = null;
  document.querySelectorAll('#fs-items .faq-item-row').forEach(row => {
    row.ondragstart = () => { dragged = row; row.classList.add('dragging'); };
    row.ondragend = () => { row.classList.remove('dragging'); };
    row.ondragover = (e) => { e.preventDefault(); };
    row.ondrop = (e) => {
      e.preventDefault();
      if (!dragged || dragged === row) return;
      const rows = Array.from(row.parentNode.children);
      if (rows.indexOf(dragged) < rows.indexOf(row)) row.after(dragged);
      else row.before(dragged);
      renderFaqSetPreview();
    };
  });
}

async function deleteFaqSet(id) {
  if (!confirm('Удалить набор? Из статей, где он вставлен, блок пропадёт.')) return;
  await api('DELETE', '/faq-sets/' + id);
  await loadAll();
}

// ═══════════════════════════════════════════════════════════════
//  ЗАГРУЗКА ДАННЫХ
// ═══════════════════════════════════════════════════════════════

async function loadAll() {
  const [cats, tr, cps, arts, tags, scs, mgs, fqs, pgs] = await Promise.all([
    api('GET', '/categories'),
    api('GET', '/trails'),
    api('GET', '/checkpoints'),
    api('GET', '/articles'),
    api('GET', '/equipment-tags'),
    api('GET', '/scenarios'),
    api('GET', '/magnets'),
    api('GET', '/faq-sets'),
    api('GET', '/site-pages'),
  ]);
  categories = cats || [];
  trails = tr || [];
  checkpoints = cps || [];
  articles = arts || [];
  equipmentTags = tags || [];
  scenarios = scs || [];
  magnets = mgs || [];
  faqSets = fqs || [];
  sitePages = pgs || [];

  renderArticles();
  renderRoutes();
  renderPlaces();
  renderScenarios();
  renderBlocks();
  renderSitePages();
}

loadAll();
