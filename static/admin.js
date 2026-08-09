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
// Заполняется из /api/districts при загрузке — список округов правится
// в админке, и выпадашки мест, маршрутов и статей должны следовать за ним.
let DISTRICT_OPTS = [];
let districts = [];
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
let difficultyLevels = [];

let activeTrail = null;      // маршрут, открытый в редакторе карты
let map = null, placeMap = null;
let vec = null;              // VectorEditor — перо и правка геометрии тропы
let cpLayers = {};           // id точки → маркер на карте маршрута
let foreignLayer = null;     // чужие места (не из этого маршрута)
let selectedSegmentId = null;
let mapClickMode = null;     // 'point' — следующий клик по карте ставит точку
let pendingPointIndex = null;   // куда вставить новую точку маршрута
let mapFittedTrailId = null;    // к какому маршруту уже подгоняли вид
let showPointLabels = true;
let showForeignPlaces = true;

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
  'place-editor': 'places',
  'districts': 'districts',
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
  installQuillFocusGuard();
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
  registerGalleryMatcher(descQuill);
  disableQuillAutoScroll(descQuill);
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
  flattenGalleryEmbeds(clone);
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
      <div class="field"><label>Проверено (актуально на)</label>
        <div style="display:flex;gap:8px">
          <input type="date" id="m-checked-at" value="${v.checked_at ? v.checked_at.slice(0, 10) : ''}" style="flex:1">
          <button type="button" class="btn btn-ghost btn-sm" onclick="document.getElementById('m-checked-at').value = new Date().toISOString().slice(0,10)">Сегодня</button>
        </div>
        <div class="hint" style="font-size:11.5px;color:var(--muted);margin-top:4px">
          Дата, которую видит гость на странице как «Актуально на …». Не выставляется сама —
          проверили маршрут или цены, тогда и обновите.
        </div>
      </div>
      <label class="toggle" style="margin-top:4px">
        <input type="checkbox" id="m-published" ${v.is_published !== false ? 'checked' : ''}>
        <span class="toggle-track"></span>
        <span class="toggle-label">Показывать на сайте
          <small>Выключите, чтобы убрать из списков и с прямой ссылки, не удаляя черновик</small>
        </span>
      </label>
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
    checked_at: document.getElementById('m-checked-at').value || null,
    is_published: document.getElementById('m-published').checked,
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
// Один и тот же файл сайт режет по-разному: в карточке это 3:2, в шапке
// страницы широкая полоса, у плитки сценария вертикальный кадр. Поэтому
// предпросмотр показывает все форматы, в которых снимок реально появится, —
// раньше рамка была одна и с произвольным соотношением 12:5, и выбранная в
// ней точка не совпадала с тем, что видел гость.
const COVER_FRAMES = {
  cover: [
    { label: 'В карточке', ratio: '3 / 2', width: 210 },
    { label: 'В шапке страницы', ratio: '12 / 5', width: 300 },
  ],
  tile: [
    { label: 'Плитка на главной', ratio: '4 / 5', width: 150 },
  ],
  // У сценария карточки нет — обложка живёт только шапкой его страницы,
  // и вторая рамка «в карточке» вводила в заблуждение.
  hero: [
    { label: 'В шапке страницы', ratio: '12 / 5', width: 300 },
  ],
  photo: [
    { label: 'В карточке', ratio: '3 / 2', width: 190 },
    { label: 'В шапке страницы', ratio: '12 / 5', width: 270 },
  ],
};

function setupCoverPreview(fileId, urlId, previewId, focusId, kind) {
  const fileEl = document.getElementById(fileId);
  const urlEl = document.getElementById(urlId);
  const boxEl = document.getElementById(previewId);
  if (!fileEl || !urlEl || !boxEl) return;
  const focusEl = focusId ? document.getElementById(focusId) : null;
  const frames = COVER_FRAMES[kind || 'cover'] || COVER_FRAMES.cover;

  // Рамки строим здесь, а не в разметке: их состав зависит от того, где
  // обложка будет показана, и держать это в трёх местах шаблона незачем.
  if (boxEl.dataset.framesBuilt !== previewId) {
    boxEl.dataset.framesBuilt = previewId;
    boxEl.classList.add('cover-frames');
    boxEl.innerHTML = frames.map(f => `
      <figure class="cover-frame-wrap" style="width:${f.width}px">
        <div class="cover-frame" style="aspect-ratio:${f.ratio}"><img alt=""></div>
        <figcaption>${f.label}</figcaption>
      </figure>`).join('');
  }
  const imgs = Array.from(boxEl.querySelectorAll('.cover-frame img'));

  function applyFocus() {
    const pos = (focusEl && focusEl.value) || '50% 50%';
    imgs.forEach(im => { im.style.objectPosition = pos; });
  }

  if (focusEl && !boxEl.dataset.dragBound) {
    boxEl.dataset.dragBound = '1';
    boxEl.classList.add('cover-frames-draggable');
    let dragging = null;
    const setFrom = (e) => {
      if (!dragging) return;
      const r = dragging.getBoundingClientRect();
      const x = Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100));
      const y = Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100));
      focusEl.value = `${Math.round(x)}% ${Math.round(y)}%`;
      applyFocus();
    };
    boxEl.addEventListener('pointerdown', (e) => {
      const frame = e.target.closest('.cover-frame');
      if (!frame) return;
      dragging = frame;
      frame.setPointerCapture(e.pointerId);
      setFrom(e);
      e.preventDefault();
    });
    boxEl.addEventListener('pointermove', setFrom);
    boxEl.addEventListener('pointerup', (e) => {
      if (dragging) {
        try { dragging.releasePointerCapture(e.pointerId); } catch (err) { /* уже отпущен */ }
      }
      dragging = null;
    });
  }

  const update = () => {
    let src = '';
    if (fileEl.files.length) src = URL.createObjectURL(fileEl.files[0]);
    else if (urlEl.value.trim()) src = urlEl.value.trim();
    boxEl.hidden = !src;
    imgs.forEach(im => { if (src) im.src = src; else im.removeAttribute('src'); });
    applyFocus();
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
  installQuillFocusGuard();
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
  registerGalleryMatcher(articleQuill);
  disableQuillAutoScroll(articleQuill);
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
  document.getElementById('a-cover-focus').value = a ? (a.cover_focus || '') : '';
  document.getElementById('a-cover-file').value = '';
  setupCoverPreview('a-cover-file', 'a-cover-url', 'a-cover-preview', 'a-cover-focus');
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
  flattenGalleryEmbeds(clone);
  return clone.innerHTML;
}

// Коллаж — это не блок с сервера, а самостоятельная разметка (см.
// registerEmbedBlots), поэтому вместо очистки, как у магнита/FAQ, здесь
// превью разворачивается обратно в голые <img> внутри <p> — именно то, что
// умеет разобрать _render_article_gallery на сервере.
function flattenGalleryEmbeds(clone) {
  clone.querySelectorAll('.gallery-embed').forEach(el => {
    const p = document.createElement('p');
    el.querySelectorAll('img').forEach(img => {
      const out = document.createElement('img');
      out.setAttribute('src', img.getAttribute('src') || '');
      const alt = img.getAttribute('alt') || '';
      if (alt) out.setAttribute('alt', alt);
      p.appendChild(out);
    });
    el.replaceWith(p);
  });
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
  document.getElementById('a-cover-focus').value = d.cover_focus || '';
  setupCoverPreview('a-cover-file', 'a-cover-url', 'a-cover-preview', 'a-cover-focus');
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

  // Если новый файл не выбирали, миниатюру берём прежнюю. Раньше здесь было
  // просто null, и любое сохранение — хоть правка заголовка — стирало
  // cover_thumb_url: карточки начинали грузить оригинал вместо превью.
  const editingArticle = articles.find(x => x.id === editingArticleId) || {};
  let coverUrl = document.getElementById('a-cover-url').value.trim();
  let coverThumb = coverUrl && coverUrl === (editingArticle.cover_url || '')
    ? (editingArticle.cover_thumb_url || null) : null;
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
    cover_focus: document.getElementById('a-cover-focus') ? (document.getElementById('a-cover-focus').value || null) : null,
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

  // Порядок в коллаже — это порядок в ленте, а браузер отдаёт файлы так, как
  // они лежали в папке. Держим кадры отдельным списком и даём двигать их
  // стрелками; подписи при перестановке едут вместе со своим фото.
  const items = chosen.map(f => ({ file: f, preview: URL.createObjectURL(f), caption: '' }));

  function renderPickRows() {
    const box = document.getElementById('pickfile-rows');
    if (!box) return;
    box.innerHTML = items.map((it, i) => `
      <div class="pickfile-item">
        ${multiple ? `<div class="pickfile-order">
          <button type="button" class="pickfile-move" onclick="movePickItem(${i}, -1)" ${i === 0 ? 'disabled' : ''} aria-label="Выше">↑</button>
          <span class="pickfile-num">${i + 1}</span>
          <button type="button" class="pickfile-move" onclick="movePickItem(${i}, 1)" ${i === items.length - 1 ? 'disabled' : ''} aria-label="Ниже">↓</button>
        </div>` : ''}
        <img src="${it.preview}" alt="">
        <div class="field">
          <label>Подпись к фото ${i + 1}</label>
          <input class="cap-input" data-idx="${i}" value="${escAttr(it.caption)}" placeholder="Можно оставить пустым">
        </div>
      </div>`).join('');
  }

  function readPickCaptions() {
    document.querySelectorAll('#pickfile-rows .cap-input').forEach(el => {
      items[Number(el.dataset.idx)].caption = el.value;
    });
  }

  // Вешаем на window: обработчики в разметке выше вызываются по имени.
  window.movePickItem = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= items.length) return;
    readPickCaptions();
    [items[i], items[j]] = [items[j], items[i]];
    renderPickRows();
  };

  // Вторая, стековая модалка — эта форма может открыться поверх уже открытой
  // (маршрут/место/сценарий), общую модалку для этого переиспользовать нельзя.
  showModal2(multiple ? 'Коллаж' : 'Фото',
    `<div class="pickfile" id="pickfile-rows"></div>${multiple ? '<div class="hint">Стрелками задайте порядок — в этом же порядке фото встанут в ленте.</div>' : ''}`,
    async () => {
    readPickCaptions();
    const caps = items.map(it => it.caption.trim());
    document.getElementById('modal2-save').disabled = true;
    document.getElementById('modal2-save').textContent = 'Загружаю...';

    const uploaded = [];
    for (let i = 0; i < items.length; i++) {
      const up = await uploadFile(items[i].file);
      if (up) uploaded.push({ url: up.url, caption: caps[i] || '' });
    }
    document.getElementById('modal2-save').disabled = false;

    if (uploaded.length) {
      // Одиночное фото без подписи остаётся обычной вставкой на всю ширину —
      // ровно то, что и раньше. Коллаж и одиночное фото С подписью вставляем
      // блоком «gallery», чтобы подпись было видно сразу в редакторе, а не
      // только в alt-атрибуте (см. registerEmbedBlots).
      if (uploaded.length === 1 && !uploaded[0].caption) {
        quill.insertEmbed(at, 'image', uploaded[0].url, 'user');
        quill.insertText(at + 1, '\n', 'user');
        quill.setSelection(at + 2);
      } else {
        quill.insertEmbed(at, 'gallery', { items: uploaded }, 'user');
        quill.setSelection(at + 1);
      }
      scheduleAutosave();
    }
    closeModal2();
  }, { saveLabel: 'Вставить' });
  renderPickRows();
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
          ${t.is_published === false ? '<span class="badge badge-draft">скрыт</span>' : ''}
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

// ── Карта: общие настройки ─────────────────────────────────────
// OSM отдаёт тайлы до 19-го зума; дальше Leaflet растягивает последний
// доступный (maxNativeZoom) — картинка мылится, зато точку можно поставить
// с точностью до пары метров, чего на 18-м зуме не хватало.
const MAP_MAX_ZOOM = 22;
const MAP_NATIVE_ZOOM = 19;
const MAP_CENTER = [44.15, 40.17];

function makeBaseLayers() {
  return {
    'Схема': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap', maxNativeZoom: MAP_NATIVE_ZOOM, maxZoom: MAP_MAX_ZOOM,
    }),
    'Спутник': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      attribution: 'Esri', maxNativeZoom: MAP_NATIVE_ZOOM, maxZoom: MAP_MAX_ZOOM,
    }),
  };
}

function createMap(elId) {
  const m = L.map(elId, {
    maxZoom: MAP_MAX_ZOOM,
    zoomSnap: 0.5,       // дробные зумы — можно подобраться к нужному масштабу
    zoomDelta: 0.5,
    wheelPxPerZoomLevel: 90,
    zoomControl: false,  // ставим сами, иначе он лезет под панель инструментов
  }).setView(MAP_CENTER, 11);
  const layers = makeBaseLayers();
  layers['Схема'].addTo(m);
  L.control.zoom({ position: 'bottomright' }).addTo(m);
  L.control.layers(layers, null, { position: 'topright' }).addTo(m);
  L.control.scale({ imperial: false }).addTo(m);
  return m;
}

function latlngsToGeojson(latlngs) {
  return { type: 'LineString', coordinates: latlngs.map(ll => [ll.lng, ll.lat]) };
}

function geojsonToLatlngs(g) {
  return ((g && g.coordinates) || []).map(([lon, lat]) => L.latLng(lat, lon));
}

function fmtLength(meters) {
  return meters >= 1000 ? (meters / 1000).toFixed(2) + ' км' : Math.round(meters) + ' м';
}

// ── Карта маршрута ─────────────────────────────────────────────
function openRouteMap(id) {
  activeTrail = trails.find(t => t.id === id);
  if (!activeTrail) return;
  showTab('route-map');
  document.getElementById('rm-title').textContent = activeTrail.name;
  document.getElementById('rm-sub').textContent = 'Перо рисует тропу, точки ставятся отдельно. Всё сохраняется сразу.';
  ensureMap();
  drawTrailOnMap();
  renderSegments();
  renderPoints();
  setHint(null);
}

function setHint(text) {
  const el = document.getElementById('rm-hint');
  el.innerHTML = text || 'Перо (P) — рисовать тропу, «Точка» (T) — поставить точку. ' +
    'Клик по нарисованному участку показывает его якоря.';
  el.classList.toggle('idle', !text);
}

function setMapStatus(text) {
  const el = document.getElementById('map-status');
  if (!el) return;
  el.textContent = text || '';
  el.hidden = !text;
}

function syncToolButtons() {
  const pen = document.getElementById('mt-pen');
  const point = document.getElementById('mt-point');
  if (pen) pen.classList.toggle('active', !!(vec && vec.drawing));
  if (point) point.classList.toggle('active', mapClickMode === 'point');
  const labels = document.getElementById('mt-labels');
  if (labels) labels.classList.toggle('active', showPointLabels);
  const foreign = document.getElementById('mt-foreign');
  if (foreign) foreign.classList.toggle('active', showForeignPlaces);
}

function ensureMap() {
  if (!map) {
    map = createMap('map');

    vec = new VectorEditor(map, {
      onCreate: createSegmentFromDraw,
      onUpdate: saveSegmentGeometry,
      onSelect: (id) => { selectedSegmentId = id; restyleSegments(); renderSegments(); syncToolButtons(); },
      onDraft: onSegmentDraft,
      onMessage: (m) => toast(m, true),
    });

    // Режим «поставить точку»: один клик — и открывается форма точки.
    map.on('click', (e) => {
      if (mapClickMode !== 'point') return;
      const atIndex = pendingPointIndex;
      stopPointMode();
      openPointForm(null, { lat: e.latlng.lat, lon: e.latlng.lng, atIndex });
    });

    // Горячие клавиши как в графических редакторах — рука не уходит с карты.
    document.addEventListener('keydown', (e) => {
      if (!document.getElementById('view-route-map').classList.contains('active')) return;
      const tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable) return;
      const k = e.key.toLowerCase();
      if (k === 'p' || k === 'з') { e.preventDefault(); startDrawSegment(); }
      else if (k === 't' || k === 'е') { e.preventDefault(); startAddPoint(null); }
      else if (e.key === 'Escape') { stopPointMode(); if (vec) vec.cancelDraw(); }
    });
  }
  setTimeout(() => map.invalidateSize(), 60);
}

function drawTrailOnMap() {
  vec.setLines(activeTrail.segments.map(s => ({
    id: s.id,
    latlngs: geojsonToLatlngs(s.geojson),
    color: DIFF_COLOR[s.difficulty] || '#888',
    weight: s.id === selectedSegmentId ? 7 : 5,
  })));

  drawCheckpointMarkers();
  drawForeignPlaces();

  // Перо липнет к точкам маршрута — тропа приходит ровно в точку, а не рядом.
  vec.setSnapTargets(activeTrail.checkpoints.map(c => L.latLng(c.lat, c.lon)));

  // Подгоняем вид один раз при открытии маршрута: иначе карта прыгала бы
  // после каждой правки и выдёргивала из масштаба, в котором рисуешь.
  if (mapFittedTrailId !== activeTrail.id) {
    mapFittedTrailId = activeTrail.id;
    fitTrail();
  }
}

function fitTrail() {
  const b = trailBoundsOf(activeTrail);
  if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50], maxZoom: 17 });
}

function drawCheckpointMarkers() {
  Object.values(cpLayers).forEach(l => map.removeLayer(l));
  cpLayers = {};

  const ordered = [...activeTrail.checkpoints].sort((a, b) => a.order_index - b.order_index);
  ordered.forEach((c, i) => {
    const m = L.marker([c.lat, c.lon], {
      icon: pointIcon(i + 1, c.show_as_place ? '#278C3E' : '#8FA391'),
      draggable: true,
      zIndexOffset: 400,
    }).addTo(map);

    // Название прямо на карте: без него на карте видны только номера и
    // непонятно, что уже расставлено.
    if (showPointLabels) {
      m.bindTooltip(c.name, {
        permanent: true, direction: 'right', offset: [12, 0], className: 'map-label',
      });
    }
    m.bindPopup(`
      <b>${escHtml(c.name)}</b><br>
      <small>${c.show_as_place ? 'показывается как место' : 'только внутри маршрута'}</small><br>
      <a href="#" onclick="openPointForm(${c.id});return false">Изменить</a> ·
      <a href="#" onclick="detachPlace(${c.id});return false">Убрать из маршрута</a>`);

    m.on('dragend', async () => {
      const ll = m.getLatLng();
      c.lat = ll.lat; c.lon = ll.lng;      // локально сразу, чтобы не мигало
      vec.setSnapTargets(activeTrail.checkpoints.map(x => L.latLng(x.lat, x.lon)));
      await api('PATCH', `/checkpoints/${c.id}`, { lat: ll.lat, lon: ll.lng });
      syncCheckpointGlobals(c);
      toast('Координаты обновлены');
    });
    cpLayers[c.id] = m;
  });
}

function pointIcon(num, color) {
  return L.divIcon({
    className: '',
    html: `<div class="map-pin" style="background:${color}">${num}</div>`,
    iconSize: [24, 24], iconAnchor: [12, 12],
  });
}

/** Чужие места на карте — чтобы видеть окружение и цеплять их к маршруту. */
function drawForeignPlaces() {
  if (foreignLayer) { map.removeLayer(foreignLayer); foreignLayer = null; }
  if (!showForeignPlaces) return;

  const others = checkpoints.filter(c => c.trail_id !== activeTrail.id);
  if (!others.length) return;

  foreignLayer = L.layerGroup().addTo(map);
  others.forEach(c => {
    const m = L.marker([c.lat, c.lon], {
      icon: L.divIcon({ className: '', html: `<div class="map-pin ghost"></div>`, iconSize: [16, 16], iconAnchor: [8, 8] }),
      zIndexOffset: 200,
    }).addTo(foreignLayer);
    m.bindTooltip(c.name, { permanent: showPointLabels, direction: 'right', offset: [9, 0], className: 'map-label ghost' });
    const where = c.trail_id
      ? `в маршруте «${escHtml((trails.find(t => t.id === c.trail_id) || {}).name || '—')}»`
      : 'отдельное место';
    m.bindPopup(`
      <b>${escHtml(c.name)}</b><br><small>${where}</small><br>
      <a href="#" onclick="attachPlaceToTrail(${c.id});return false">Добавить в этот маршрут</a> ·
      <a href="#" onclick="openPointForm(${c.id});return false">Изменить</a>`);
  });
}

function toggleLabels() {
  showPointLabels = !showPointLabels;
  drawCheckpointMarkers();
  drawForeignPlaces();
  syncToolButtons();
}

function toggleForeign() {
  showForeignPlaces = !showForeignPlaces;
  drawForeignPlaces();
  syncToolButtons();
}

/** Забирает место в текущий маршрут — привязка, которой раньше не было. */
async function attachPlaceToTrail(cpId) {
  if (!activeTrail) return;
  map.closePopup();
  const saved = await api('PATCH', `/checkpoints/${cpId}`, { trail_id: activeTrail.id });
  if (!saved) return;
  await reloadActiveTrail();
  toast('Место добавлено в маршрут');
}

async function detachPlace(cpId) {
  map.closePopup();
  if (!confirm('Убрать точку из маршрута? Она останется как отдельное место.')) return;
  const saved = await api('PATCH', `/checkpoints/${cpId}`, { trail_id: null });
  if (!saved) return;
  await reloadActiveTrail();
  toast('Точка теперь отдельное место');
}

/**
 * Лёгкое обновление: тянем один маршрут вместо всей базы.
 * Раньше здесь был loadAll() — девять запросов и перерисовка всех списков
 * после каждого клика, отсюда и бралась задержка на карте.
 */
async function reloadActiveTrail() {
  if (!activeTrail) return;
  const fresh = await api('GET', `/trails/${activeTrail.id}`);
  if (!fresh) return;
  const i = trails.findIndex(t => t.id === fresh.id);
  if (i >= 0) trails[i] = fresh; else trails.push(fresh);
  checkpoints = checkpoints.filter(c => c.trail_id !== fresh.id).concat(fresh.checkpoints);
  activeTrail = fresh;

  drawTrailOnMap();
  renderSegments();
  renderPoints();
  renderRoutes();
  renderPlaces();
}

function syncCheckpointGlobals(cp) {
  const i = checkpoints.findIndex(x => x.id === cp.id);
  if (i >= 0) checkpoints[i] = Object.assign({}, checkpoints[i], cp);
  else checkpoints.push(cp);
}

// ── Перо: рисование и правка участков ──────────────────────────
function startDrawSegment() {
  stopPointMode();
  const diff = document.getElementById('rm-seg-difficulty').value;
  vec.startDraw({ color: DIFF_COLOR[diff] });
  setHint('<b>Перо.</b> Клик — узел, тянется резинка. Shift — угол кратен 15°, ' +
          'Backspace — убрать последний узел, двойной клик или Enter — закончить, Esc — отменить. ' +
          'Начните с конца готового участка, чтобы продолжить его.');
  syncToolButtons();
}

function onSegmentDraft(d) {
  if (!d) { setMapStatus(null); setHint(null); syncToolButtons(); return; }
  const parts = [`Узлов: ${d.count}`];
  if (d.length) parts.push(fmtLength(d.length));
  if (d.extending) parts.push('продолжаем участок');
  setMapStatus(parts.join(' · '));
  syncToolButtons();
}

async function createSegmentFromDraw(latlngs) {
  setMapStatus(null);
  const saved = await api('POST', `/trails/${activeTrail.id}/segments`, {
    difficulty: document.getElementById('rm-seg-difficulty').value,
    order_index: activeTrail.segments.length,
    geojson: latlngsToGeojson(latlngs),
  });
  if (!saved) return;
  // Дописываем в локальное состояние — перерисовывать всю карту незачем.
  activeTrail.segments.push(saved);
  selectedSegmentId = saved.id;
  drawTrailOnMap();
  renderSegments();
  vec.select(saved.id);
}

/** Выделенный участок делаем толще — видно, чьи якоря сейчас на карте. */
function restyleSegments() {
  vec.lines.forEach((line, id) => line.poly.setStyle({ weight: id === selectedSegmentId ? 7 : 5 }));
}

async function saveSegmentGeometry(id, latlngs) {
  const seg = activeTrail.segments.find(s => s.id === id);
  const geojson = latlngsToGeojson(latlngs);
  if (seg) seg.geojson = geojson;              // на экране уже так, сохраняем следом
  const len = fmtLength(vecPathLength(latlngs));
  setMapStatus(len + ' · сохраняю…');
  const saved = await api('PATCH', `/segments/${id}`, { geojson });
  setMapStatus(saved ? len + ' · сохранено' : null);
  if (saved) renderSegments();
}

function renderSegments() {
  const el = document.getElementById('rm-segments');
  if (!activeTrail.segments.length) {
    el.innerHTML = `<div class="hint" style="color:var(--muted);font-size:12.5px">Тропа ещё не нарисована. Нажмите «Перо» и ведите линию по карте.</div>`;
    return;
  }
  el.innerHTML = activeTrail.segments.map((s, i) => {
    const len = fmtLength(vecPathLength(geojsonToLatlngs(s.geojson)));
    return `
    <div class="seg ${s.id === selectedSegmentId ? 'selected' : ''}" onclick="selectSegment(${s.id})">
      <span class="seg-dot ${s.difficulty}"></span>
      <span class="seg-name">Участок ${i + 1}<small>${len}</small></span>
      <select onclick="event.stopPropagation()" onchange="changeSegmentDifficulty(${s.id}, this.value)">
        ${optionsHtml(DIFFICULTY_OPTS, s.difficulty)}
      </select>
      <button class="btn btn-danger btn-sm" onclick="event.stopPropagation();deleteSegment(${s.id})">×</button>
    </div>`;
  }).join('');
}

function selectSegment(id) {
  vec.select(id);
  const line = vec.lines.get(id);
  if (line) {
    const b = line.poly.getBounds();
    if (b.isValid() && !map.getBounds().contains(b)) map.fitBounds(b, { padding: [60, 60] });
  }
}

async function changeSegmentDifficulty(id, difficulty) {
  const seg = activeTrail.segments.find(s => s.id === id);
  if (seg) seg.difficulty = difficulty;
  drawTrailOnMap();
  renderSegments();
  await api('PATCH', `/segments/${id}`, { difficulty });
}

async function deleteSegment(id) {
  if (!confirm('Удалить участок тропы?')) return;
  await api('DELETE', `/segments/${id}`);
  activeTrail.segments = activeTrail.segments.filter(s => s.id !== id);
  if (selectedSegmentId === id) selectedSegmentId = null;
  drawTrailOnMap();
  renderSegments();
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
      await reloadActiveTrail();
    });
  });
}

function startAddPoint(atIndex) {
  if (vec) vec.cancelDraw();
  mapClickMode = 'point';
  pendingPointIndex = atIndex;
  L.DomUtil.addClass(map.getContainer(), 'vec-drawing');
  setHint(atIndex === null || atIndex === undefined
    ? 'Кликните на карте, чтобы поставить точку в конец маршрута. Esc — отмена.'
    : `Кликните на карте — точка встанет на позицию ${atIndex + 1}. Esc — отмена.`);
  syncToolButtons();
}

function stopPointMode() {
  if (mapClickMode !== 'point') return;
  mapClickMode = null;
  pendingPointIndex = null;
  L.DomUtil.removeClass(map.getContainer(), 'vec-drawing');
  setHint(null);
  syncToolButtons();
}

function focusPoint(id) {
  const m = cpLayers[id];
  if (m) { map.setView(m.getLatLng(), 17); m.openPopup(); }
}

async function togglePointPublic(id, checked) {
  const saved = await api('PATCH', `/checkpoints/${id}`, { show_as_place: checked });
  if (!saved) return;
  const cp = activeTrail.checkpoints.find(c => c.id === id);
  if (cp) cp.show_as_place = checked;
  syncCheckpointGlobals({ id, show_as_place: checked });
  drawCheckpointMarkers();
  renderPoints();
  renderPlaces();
  toast(checked ? 'Точка показывается в «Местах»' : 'Точка убрана из «Мест»');
}

async function deletePoint(id) {
  if (!confirm('Удалить точку?')) return;
  await api('DELETE', `/checkpoints/${id}`);
  activeTrail.checkpoints = activeTrail.checkpoints.filter(c => c.id !== id);
  checkpoints = checkpoints.filter(c => c.id !== id);
  drawCheckpointMarkers();
  renderPoints();
  renderPlaces();
}

// ── Редактор точки / места ─────────────────────────────────────
// Такая же полноэкранная вкладка, как у статьи, маршрута и сценария: описание
// места — полноценный текст со вставками, и набирать его в модалке на треть
// экрана неудобно.
let editingPlaceId = null;
let placeCreating = null;    // {atIndex, standalone} для новой точки
let placeDraftScope = null;
let placeCoords = null;      // {lat, lon} — редактируется на карте прямо в форме
let placeMarker = null;
// Куда вернуться по «Назад» и после сохранения: точку заводят и из списка
// мест, и с карты маршрута — возвращать надо туда, откуда пришли.
let placeReturnView = 'places';

function openPointForm(id, creating) {
  releaseSlots(DESC_EDITOR_SLOTS, 'pl-desc-slot');
  releaseSlots(CRITERIA_SLOTS, 'pl-criteria-slot');
  const c = id ? checkpoints.find(x => x.id === id) : null;
  const v = c || {};

  editingPlaceId = c ? c.id : null;
  placeCreating = c ? null : (creating || {});
  placeDraftScope = 'place:' + (c ? c.id : 'new');
  placeReturnView = document.getElementById('view-route-map').classList.contains('active')
    ? 'route-map' : 'places';

  // Маршрут точки: у новой берём тот, с карты которого её ставят.
  const trailId = c ? c.trail_id
    : (placeCreating.standalone ? null : (activeTrail ? activeTrail.id : null));
  const showAsPlace = c ? c.show_as_place : !trailId;

  // Тумблер «отдельной точкой» показываем всегда: маршрут теперь меняется
  // прямо здесь, и переключатель должен уметь появиться без перерисовки формы.
  const publishExtra = `
    <label class="toggle" style="margin-top:4px" id="m-show-place-row">
      <input type="checkbox" id="m-show-place" ${showAsPlace ? 'checked' : ''}>
      <span class="toggle-track"></span>
      <span class="toggle-label">Выделить отдельной точкой
        <small>Точка получит свою страницу и попадёт в раздел «Места». Без этого она видна только внутри маршрута.</small>
      </span>
    </label>`;

  showTab('place-editor');
  document.getElementById('pl-name').value = v.name || '';
  document.getElementById('pl-category').innerHTML = categoryOptionsHtml('checkpoint', v.category_id);
  document.getElementById('pl-duration').value = v.duration_minutes || '';
  document.getElementById('pl-trail').innerHTML =
    `<option value="">— отдельное место —</option>` +
    trails.map(t => `<option value="${t.id}" ${t.id === trailId ? 'selected' : ''}>${escHtml(t.name)}</option>`).join('');
  document.getElementById('pl-desc-slot').innerHTML = descEditorHtml('Описание');
  document.getElementById('pl-criteria-slot').innerHTML = criteriaHtml(v, { extraPublishHtml: publishExtra });

  initDescEditor(v.description || '', placeDraftScope);
  autoGrow(document.getElementById('pl-name'));
  setSaveState('', false, 'pl-save-state');

  placeCoords = (c && c.lat != null) ? { lat: c.lat, lon: c.lon }
    : (creating && creating.lat != null) ? { lat: creating.lat, lon: creating.lon }
    : null;
  syncPlaceTrailUi();
  setupPlaceEditorMap();
}

/** Без маршрута точка обязана быть местом — иначе она нигде не видна. */
function syncPlaceTrailUi() {
  const trailId = document.getElementById('pl-trail').value;
  const toggle = document.getElementById('m-show-place');
  if (!toggle) return;
  if (!trailId) {
    toggle.checked = true;
    toggle.disabled = true;
    toggle.closest('.toggle').classList.add('locked');
  } else {
    toggle.disabled = false;
    toggle.closest('.toggle').classList.remove('locked');
  }
}

function onPlaceTrailChange() {
  syncPlaceTrailUi();
  schedulePlaceAutosave();
}

// ── Карта прямо в форме места ──────────────────────────────────
function setupPlaceEditorMap() {
  if (!placeMap) {
    placeMap = createMap('pl-map');
    placeMap.on('click', (e) => setPlaceCoords(e.latlng.lat, e.latlng.lng));
  }
  if (placeMarker) { placeMap.removeLayer(placeMarker); placeMarker = null; }

  if (placeCoords) {
    addPlaceMarker();
    placeMap.setView([placeCoords.lat, placeCoords.lon], Math.max(placeMap.getZoom(), 16));
  } else if (activeTrail && trailBoundsOf(activeTrail)) {
    placeMap.fitBounds(trailBoundsOf(activeTrail), { padding: [40, 40], maxZoom: 15 });
  } else {
    placeMap.setView(MAP_CENTER, 10);
  }
  updatePlaceCoordsLabel();
  // Вкладка была скрыта, пока строилась — Leaflet должен пересчитать размер.
  setTimeout(() => placeMap.invalidateSize(), 80);
}

function trailBoundsOf(trail) {
  const pts = [];
  (trail.segments || []).forEach(s => geojsonToLatlngs(s.geojson).forEach(ll => pts.push(ll)));
  (trail.checkpoints || []).forEach(c => pts.push(L.latLng(c.lat, c.lon)));
  return pts.length ? L.latLngBounds(pts) : null;
}

function addPlaceMarker() {
  placeMarker = L.marker([placeCoords.lat, placeCoords.lon], {
    icon: pointIcon('', '#278C3E'),
    draggable: true,
  }).addTo(placeMap);
  placeMarker.on('drag', () => {
    const ll = placeMarker.getLatLng();
    placeCoords = { lat: ll.lat, lon: ll.lng };
    updatePlaceCoordsLabel();
  });
  placeMarker.on('dragend', () => schedulePlaceAutosave());
}

function setPlaceCoords(lat, lon) {
  placeCoords = { lat, lon };
  if (placeMarker) placeMarker.setLatLng([lat, lon]);
  else addPlaceMarker();
  updatePlaceCoordsLabel();
  schedulePlaceAutosave();
}

function updatePlaceCoordsLabel() {
  const el = document.getElementById('pl-coords');
  if (!el) return;
  el.textContent = placeCoords
    ? `${placeCoords.lat.toFixed(6)}, ${placeCoords.lon.toFixed(6)}`
    : 'Место на карте не отмечено — кликните по карте';
  el.classList.toggle('warn', !placeCoords);
}

/** Ручной ввод координат — их часто копируют из чужой карты или из GPS. */
function pastePlaceCoords() {
  const raw = prompt('Координаты через запятую (широта, долгота)',
    placeCoords ? `${placeCoords.lat.toFixed(6)}, ${placeCoords.lon.toFixed(6)}` : '');
  if (!raw) return;
  const m = raw.replace(',', ' ').split(/[\s;]+/).filter(Boolean).map(Number);
  if (m.length < 2 || !isFinite(m[0]) || !isFinite(m[1])) { toast('Не разобрал координаты', true); return; }
  setPlaceCoords(m[0], m[1]);
  placeMap.setView([m[0], m[1]], Math.max(placeMap.getZoom(), 16));
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

  const trailId = parseInt(document.getElementById('pl-trail').value, 10) || null;
  payload.trail_id = trailId;
  if (placeCoords) { payload.lat = placeCoords.lat; payload.lon = placeCoords.lon; }

  if (!payload.name) { toast('Введите название', true); return; }
  if (!placeCoords) { toast('Отметьте место на карте', true); return; }

  const creating = placeCreating;
  let saved;
  if (editingPlaceId) {
    saved = await api('PATCH', `/checkpoints/${editingPlaceId}`, payload);
  } else {
    payload.order_index = trailId ? (trails.find(t => t.id === trailId) || { checkpoints: [] }).checkpoints.length : 0;
    saved = await api('POST', '/checkpoints', payload);

    // Вставка в середину: создаём в конце, потом двигаем на нужное место.
    if (saved && creating && creating.atIndex !== null && creating.atIndex !== undefined && trailId) {
      const trail = trails.find(t => t.id === trailId);
      const ordered = [...(trail ? trail.checkpoints : [])].sort((a, b) => a.order_index - b.order_index).map(x => x.id);
      ordered.splice(creating.atIndex, 0, saved.id);
      await api('PATCH', `/trails/${trailId}/checkpoints/order`, { ids: ordered });
    }
  }
  if (!saved) return;

  clearDescDraft(placeDraftScope);
  syncCheckpointGlobals(saved);
  const wasNew = !editingPlaceId;
  editingPlaceId = saved.id;
  placeCreating = null;
  placeDraftScope = 'place:' + saved.id;
  toast('Сохранено');

  if (activeTrail && placeReturnView === 'route-map') {
    await reloadActiveTrail();
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

// «Места на сайте» — отдельные карточки (show_as_place); «Точки маршрутов» —
// все точки внутри маршрутов, включая ещё не выделенные в места. Раньше
// вторых нигде не было видно вне карты конкретного маршрута.
let placesSubtab = 'public';

function switchPlacesSubtab(tab) {
  placesSubtab = tab;
  document.getElementById('places-subtab-public').classList.toggle('active', tab === 'public');
  document.getElementById('places-subtab-trail').classList.toggle('active', tab === 'trail');
  document.getElementById('places-search').placeholder = tab === 'trail' ? 'Найти точку...' : 'Найти место...';
  document.getElementById('places-add-btn').style.display = tab === 'trail' ? 'none' : '';
  document.getElementById('places-sub').textContent = tab === 'trail'
    ? 'Все точки внутри маршрутов — включая те, что ещё не выделены отдельным местом'
    : 'Всё, что показывается на сайте отдельными карточками';
  renderPlaces();
}

function renderPlaces() {
  if (placesSubtab === 'trail') { renderTrailPoints(); return; }
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
          ${c.is_published === false ? '<span class="badge badge-draft">скрыт</span>' : ''}
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

function renderTrailPoints() {
  const q = (document.getElementById('places-search').value || '').toLowerCase();
  const list = checkpoints
    .filter(c => c.trail_id != null)
    .filter(c => !q || c.name.toLowerCase().includes(q))
    .sort((a, b) => {
      const ta = (trails.find(t => t.id === a.trail_id) || {}).name || '';
      const tb = (trails.find(t => t.id === b.trail_id) || {}).name || '';
      return ta.localeCompare(tb, 'ru') || a.order_index - b.order_index;
    });
  const el = document.getElementById('places-list');
  if (!list.length) {
    el.innerHTML = `<div class="empty"><b>Точек нет</b>Добавляются кнопкой «Карта и точки» у маршрута.</div>`;
    return;
  }
  el.innerHTML = list.map(c => {
    const cover = (c.photos && c.photos.length) ? c.photos[0].thumb_url || c.photos[0].url : '';
    const trail = trails.find(t => t.id === c.trail_id);
    return `
    <div class="row">
      <div class="row-thumb" style="${cover ? `background-image:url('${escAttr(cover)}')` : ''}"></div>
      <div class="row-main">
        <div class="row-title">${escHtml(c.name)}
          ${c.is_published === false ? '<span class="badge badge-draft">скрыт</span>' : ''}
          <span class="badge">${trail ? escHtml(trail.name) : '— без маршрута —'}</span>
          ${c.show_as_place ? '<span class="badge badge-green">видна как место</span>' : ''}
        </div>
        <div class="row-meta">
          <span>${escHtml(categoryLabel(c.category))}</span>
          <span>№ ${c.order_index + 1} по маршруту</span>
        </div>
      </div>
      <div class="row-actions">
        ${trail ? `<button class="btn btn-ghost btn-sm" onclick="openRouteMap(${trail.id})">На карте маршрута</button>` : ''}
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

// Раньше новое место сначала требовало ткнуть в отдельный экран с картой и
// только потом пускало в форму. Теперь карта живёт внутри самой формы —
// название, описание и точка ставятся в одном месте и в любом порядке.
function startAddStandalonePlace() {
  openPointForm(null, { standalone: true, atIndex: null });
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
      Первое фото становится обложкой на карточке и в соцсетях. Подпись видна
      под фото в карусели на странице места/маршрута — без неё просто фото без текста.
    </div>
    <div class="photos" id="photo-grid">
      ${photos.map((p, i) => `
        <div class="photo">
          <img src="${escAttr(p.thumb_url || p.url)}" alt=""${i === 0 ? ' style="object-position:' + escAttr(p.focus || '50% 50%') + '"' : ''}>
          <button onclick="deletePhoto(${p.id}, '${kind}', ${id})">×</button>
          <input type="text" class="photo-caption" placeholder="Подпись (необязательно)"
                 value="${escAttr(p.caption || '')}"
                 onchange="savePhotoCaption(${p.id}, this.value)">
          ${i === 0 ? `<button type="button" class="btn btn-ghost btn-sm photo-crop"
                 onclick="openPhotoCrop(${p.id}, '${escAttr(p.url)}', '${escAttr(p.focus || '')}')">Кадрировать обложку</button>` : ''}
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
    if (activeTrail && document.getElementById('view-route-map').classList.contains('active')) reloadActiveTrail();
    renderPlaces(); renderRoutes();
  }, { saveLabel: 'Загрузить' });
}

function openPhotoCrop(photoId, url, focus) {
  showModal2('Кадр обложки', `
    <div class="hint" style="margin-bottom:10px">Потяните по любой рамке — обе показывают, каким этот кадр увидит гость.</div>
    <input type="hidden" id="ph-crop-url" value="${escAttr(url)}">
    <input type="hidden" id="ph-crop-focus" value="${escAttr(focus)}">
    <input type="file" id="ph-crop-file" style="display:none">
    <div class="cover-preview" id="ph-crop-preview"></div>
  `, async () => {
    const value = document.getElementById('ph-crop-focus').value || null;
    await api('PATCH', `/photos/${photoId}`, { focus: value });
    closeModal2();
    toast('Кадр сохранён');
  }, { saveLabel: 'Сохранить' });
  setupCoverPreview('ph-crop-file', 'ph-crop-url', 'ph-crop-preview', 'ph-crop-focus', 'photo');
}

async function savePhotoCaption(photoId, caption) {
  const saved = await api('PATCH', `/photos/${photoId}`, { caption: caption.trim() || null });
  if (saved) toast('Подпись сохранена');
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
  document.getElementById('sc-cover-focus').value = v.cover_focus || '';
  document.getElementById('sc-cover-file').value = '';
  document.getElementById('sc-tile-cover-url').value = v.tile_cover_url || '';
  document.getElementById('sc-tile-cover-focus').value = v.tile_cover_focus || '';
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

  setupCoverPreview('sc-cover-file', 'sc-cover-url', 'sc-cover-preview', 'sc-cover-focus', 'hero');
  setupCoverPreview('sc-tile-cover-file', 'sc-tile-cover-url', 'sc-tile-cover-preview', 'sc-tile-cover-focus', 'tile');
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

  // Та же история, что у статьи: без выбора нового файла миниатюра
  // затиралась в null, и плитка сценария на главной начинала тянуть
  // оригинал — именно поэтому обложка «Впервые в Адыгею» весила 383 КБ.
  const editingScenario = scenarios.find(x => x.id === editingScenarioId) || {};
  let coverUrl = document.getElementById('sc-cover-url').value.trim();
  let coverThumb = coverUrl && coverUrl === (editingScenario.cover_url || '')
    ? (editingScenario.cover_thumb_url || null) : null;
  const coverFileEl = document.getElementById('sc-cover-file');
  if (coverFileEl.files.length) {
    const up = await uploadFile(coverFileEl.files[0]);
    if (up) { coverUrl = up.url; coverThumb = up.thumb_url; }
  }

  let tileCoverUrl = document.getElementById('sc-tile-cover-url').value.trim();
  let tileCoverThumb = tileCoverUrl && tileCoverUrl === (editingScenario.tile_cover_url || '')
    ? (editingScenario.tile_cover_thumb_url || null) : null;
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
    cover_focus: document.getElementById('sc-cover-focus').value || null,
    tile_cover_focus: document.getElementById('sc-tile-cover-focus').value || null,
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

  // Коллаж/фото с подписью — в отличие от магнита и набора вопросов, сюда
  // не подставляется ничего с сервера: на сайте это просто несколько <img>
  // подряд в одном <p> (см. _render_article_gallery в site_app/router.py),
  // сервер группирует их в галерею сам. Здесь блот нужен только чтобы то же
  // самое было видно уже в редакторе — при сохранении (readArticleBody/
  // readDescEditor) он разворачивается обратно в голые <img>, а не остаётся
  // пустым контейнером.
  class GalleryBlot extends BlockEmbed {
    static create(value) {
      const node = super.create();
      node.setAttribute('contenteditable', 'false');
      const items = (value && value.items) || [];
      if (items.length >= 2) {
        const total = items.length;
        node.innerHTML = '<div class="editor-gallery-track">' + items.map((it, i) => {
          const cap = (it.caption || '').trim();
          const capHtml = cap
            ? '<figcaption class="editor-gallery-caption"><span class="editor-gallery-counter">' + (i + 1) + '/' + total + '</span><span class="editor-gallery-text">' + escHtml(cap) + '</span></figcaption>'
            : '';
          return '<figure class="editor-gallery-item"><img src="' + escAttr(it.url) + '" alt="' + escAttr(cap) + '">' + capHtml + '</figure>';
        }).join('') + '</div>';
      } else {
        node.classList.add('single');
        const it = items[0] || { url: '', caption: '' };
        const cap = (it.caption || '').trim();
        node.innerHTML = '<img src="' + escAttr(it.url) + '" alt="' + escAttr(cap) + '">' +
          (cap ? '<figcaption>' + escHtml(cap) + '</figcaption>' : '');
      }
      return node;
    }
    static value(node) {
      const items = Array.from(node.querySelectorAll('img')).map(img => ({
        url: img.getAttribute('src') || '',
        caption: img.getAttribute('alt') || '',
      }));
      return { items };
    }
  }
  GalleryBlot.blotName = 'gallery';
  GalleryBlot.tagName = 'div';
  GalleryBlot.className = 'gallery-embed';

  Quill.register(MagnetBlot);
  Quill.register(FaqBlot);
  Quill.register(ConsiderBlot);
  Quill.register(GalleryBlot);
  window.__embedBlotsRegistered = true;
}

// При загрузке уже сохранённой статьи Quill парсит её HTML заново, и без этой
// подсказки коллаж (несколько <img> подряд в одном <p>) снова превратился бы
// в голые картинки без подписи — ровно баг, который этот блот и чинит.
// Одиночное фото без подписи матчер не трогает — оно и на сайте, и в
// редакторе остаётся обычной вставкой на всю ширину.
function registerGalleryMatcher(quill) {
  const Delta = Quill.import('delta');
  quill.clipboard.addMatcher('p', (node, delta) => {
    const children = Array.from(node.childNodes);
    const onlyImgs = children.length > 0 && children.every(n =>
      (n.nodeType === 1 && n.tagName === 'IMG') || (n.nodeType === 3 && !n.textContent.trim()));
    if (!onlyImgs) return delta;
    const imgs = children.filter(n => n.nodeType === 1 && n.tagName === 'IMG');
    if (!imgs.length) return delta;
    const items = imgs.map(img => ({
      url: img.getAttribute('src') || '',
      caption: (img.getAttribute('alt') || '').trim(),
    }));
    if (items.length === 1 && !items[0].caption) return delta;
    return new Delta().insert({ gallery: { items } });
  });
}

// Quill возвращает фокус в редактор вызовом focus() без preventScroll, а такой
// вызов браузер понимает как «прокрути к этому элементу». Лист статьи — это
// один элемент высотой в несколько тысяч пикселей, целиком в окно он не
// помещается, поэтому браузер показывает его начало: текст уезжает в самый
// верх, хотя курсор остался в середине.
//
// Мест, откуда это прилетает, больше двух, и они разные:
//   • root.focus() — после клика по тулбару (заголовок, список, цитата);
//   • clipboard.container.focus() — при вставке из буфера: Quill на кадр
//     перекидывает фокус в скрытый .ql-clipboard, у которого left:-100000px;
//   • textbox.focus() у всплывающей подсказки — при вставке ссылки.
// Патчить их поимённо оказалось ненадёжно: следующий такой вызов внутри Quill
// снова проходит мимо. Поэтому подменяем focus один раз на прототипе и
// включаем preventScroll для всего, что лежит внутри редактора, — какой бы
// элемент Quill ни сфокусировал, скролл останется на месте.
//
// Патч намеренно узкий: за пределами .ql-container фокус работает как обычно,
// и переход к полю в длинной форме по-прежнему к нему прокручивает.
//
// Но одного focus мало. Второй источник — сам Quill: setSelection() в конце
// зовёт selection.scrollIntoView(), которая прямым присваиванием scrollTop
// подтягивает курсор к краю. Это не focus и preventScroll её не касается —
// именно она уводила текст вниз при вставке. Её глушим на каждом редакторе.
//
// Третьим слоем идёт страховка: перед любым действием, которое не является
// набором текста (клик по тулбару, вставка из буфера, вставка блока через
// модалку), запоминаем прокрутку окна и всех скроллящихся родителей и
// возвращаем её на ближайших кадрах, если что-то всё-таки сдвинуло. Так
// положение не меняется, даже если внутри Quill появится ещё один источник
// прокрутки, о котором мы не знаем.
let quillFocusGuardInstalled = false;

function installQuillFocusGuard() {
  if (quillFocusGuardInstalled) return;
  quillFocusGuardInstalled = true;

  const nativeFocus = HTMLElement.prototype.focus;
  HTMLElement.prototype.focus = function (options) {
    if (this.closest && this.closest('.ql-container')) {
      // Явно переданный preventScroll уважаем — наш здесь только значение
      // по умолчанию, которого Quill не задаёт.
      return nativeFocus.call(this, Object.assign({ preventScroll: true }, options));
    }
    return nativeFocus.call(this, options);
  };

  // Клик по тулбару, всплывающей подсказке, плавающему «+», панели вставки и
  // кнопкам модалки. Набор текста сюда не попадает: печать идёт без mousedown,
  // и родное подтягивание каретки к краю экрана продолжает работать.
  const ARMS = '.ql-toolbar, .ql-tooltip, .insert-plus, .insert-menu, .insert-bar, .modal-backdrop';
  document.addEventListener('mousedown', (e) => {
    if (e.target.closest && e.target.closest(ARMS)) holdScroll();
  }, true);
  document.addEventListener('paste', (e) => {
    if (e.target.closest && e.target.closest('.ql-container')) holdScroll();
  }, true);
}

// Глушилка собственной прокрутки Quill — по одной на редактор.
function disableQuillAutoScroll(quill) {
  if (quill && quill.selection) quill.selection.scrollIntoView = function () {};
}

// Держит прокрутку неизменной несколько кадров: вставка блока через модалку
// доезжает не мгновенно, а через два-три кадра после клика по «Вставить».
function holdScroll(ms = 700) {
  const marks = [[window, window.scrollX, window.scrollY]];
  document.querySelectorAll('.modal-body, .editor-shell, .ql-container').forEach((el) => {
    if (el.scrollHeight > el.clientHeight) marks.push([el, el.scrollLeft, el.scrollTop]);
  });

  const restore = () => {
    marks.forEach(([el, x, y]) => {
      if (el === window) {
        if (window.scrollY !== y || window.scrollX !== x) window.scrollTo(x, y);
      } else if (el.scrollTop !== y || el.scrollLeft !== x) {
        el.scrollTop = y;
        el.scrollLeft = x;
      }
    });
  };

  const until = performance.now() + ms;
  const tick = () => {
    restore();
    if (performance.now() < until) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
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

const SITE_PAGE_LABELS = { home: 'Главная страница', club: 'Страница клуба', difficulty: 'Подсказка «Сложность»' };

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

function renderDistricts() {
  const el = document.getElementById('districts-list');
  if (!el) return;
  el.innerHTML = districts.map(d => `
    <div class="row">
      <div class="row-thumb" style="${d.cover_thumb_url || d.cover_url ? `background-image:url('${escAttr(d.cover_thumb_url || d.cover_url)}')` : ''}"></div>
      <div class="row-main">
        <div class="row-title">${escHtml(d.name)}${d.is_published === false ? ' <span class="badge">скрыт</span>' : ''}</div>
        <div class="row-meta"><span>/okrugi/${escHtml(d.slug)}</span><span>${(d.facts || []).length} фактов</span></div>
      </div>
      <div class="row-actions">
        <button class="btn btn-ghost btn-sm" onclick="openDistrictForm(${d.id})">Редактировать</button>
        <button class="btn btn-ghost btn-sm" onclick="removeDistrict(${d.id})">Удалить</button>
      </div>
    </div>`).join('');
}

function districtFactRow(v) {
  return `<div class="tip-row"><input class="dist-fact" value="${escAttr(v || '')}" placeholder="Короткий факт об округе">
    <button type="button" class="btn btn-ghost btn-sm" onclick="this.parentElement.remove()">×</button></div>`;
}

function addDistrictFact() {
  document.getElementById('dist-facts').insertAdjacentHTML('beforeend', districtFactRow(''));
}

function openDistrictForm(id) {
  const d = districts.find(x => x.id === id) || {};
  const isNew = !d.id;
  showModal(isNew ? 'Новый округ' : `Округ: ${d.name}`, `
    <div class="field"><label>Название</label>
      <input id="dist-name" value="${escAttr(d.name || '')}" placeholder="Округ Хаджоха"></div>
    <div class="field"><label>Адрес страницы</label>
      <input id="dist-slug" value="${escAttr(d.slug || '')}" placeholder="khadzhokh" ${isNew ? '' : 'disabled'}>
      <div class="hint">${isNew ? 'Латиницей. Потом не меняется: к нему привязаны места, маршруты и статьи.' : 'Адрес не меняется — к нему привязаны места, маршруты и статьи.'}</div></div>
    <div class="field"><label>Вступление</label>
      <textarea id="dist-lead" rows="4" placeholder="Чем этот округ полезен в поездке">${escHtml(d.lead || '')}</textarea></div>
    <div class="field"><label>Факты</label>
      <div id="dist-facts">${((d.facts && d.facts.length) ? d.facts : ['']).map(districtFactRow).join('')}</div>
      <button type="button" class="btn btn-ghost btn-sm" onclick="addDistrictFact()">+ Факт</button>
      <div class="hint">Показываются списком на странице округа.</div></div>
    <div class="field"><label>Обложка</label>
      <input type="file" id="dist-cover-file" accept="image/*">
      <input type="hidden" id="dist-cover-url" value="${escAttr(d.cover_url || '')}">
      <input type="hidden" id="dist-cover-focus" value="${escAttr(d.cover_focus || '')}">
      <div id="dist-cover-preview" class="cover-preview" hidden></div>
      <div class="hint">Потяните по картинке, чтобы выбрать видимую часть кадра.</div></div>
    <div class="field"><label class="check"><input type="checkbox" id="dist-published" ${d.is_published === false ? '' : 'checked'}> Показывать на сайте</label></div>
  `, async () => {
    const name = document.getElementById('dist-name').value.trim();
    if (!name) { toast('Название обязательно', true); return; }
    let coverUrl = document.getElementById('dist-cover-url').value || null;
    let coverThumb = d.cover_thumb_url || null;
    const fileEl = document.getElementById('dist-cover-file');
    if (fileEl.files.length) {
      const up = await uploadFile(fileEl.files[0]);
      if (up) { coverUrl = up.url; coverThumb = up.thumb_url; }
    }
    const payload = {
      name,
      lead: document.getElementById('dist-lead').value.trim(),
      facts: Array.from(document.querySelectorAll('#dist-facts .dist-fact')).map(e => e.value.trim()).filter(Boolean),
      cover_url: coverUrl,
      cover_thumb_url: coverThumb,
      cover_focus: document.getElementById('dist-cover-focus').value || null,
      is_published: document.getElementById('dist-published').checked,
    };
    if (isNew) {
      payload.slug = document.getElementById('dist-slug').value.trim();
      if (!payload.slug) { toast('Нужен адрес страницы', true); return; }
      payload.order_index = districts.length;
      districts.push(await api('POST', '/districts', payload));
    } else {
      Object.assign(d, await api('PATCH', `/districts/${d.id}`, payload));
    }
    refreshDistrictOpts();
    renderDistricts();
    closeModal();
    toast('Сохранено');
  });
  setupCoverPreview('dist-cover-file', 'dist-cover-url', 'dist-cover-preview', 'dist-cover-focus');
}

async function removeDistrict(id) {
  const d = districts.find(x => x.id === id);
  if (!d || !confirm(`Удалить округ «${d.name}»?`)) return;
  try {
    await api('DELETE', `/districts/${id}`);
    districts = districts.filter(x => x.id !== id);
    refreshDistrictOpts();
    renderDistricts();
    toast('Удалено');
  } catch (e) {
    toast(e.message || 'Не удалось удалить', true);
  }
}

function refreshDistrictOpts() {
  DISTRICT_OPTS = districts.map(d => ({ code: d.slug, label: d.name }));
}

function renderDifficultyList() {
  const el = document.getElementById('difficulty-list');
  if (!el) return;
  el.innerHTML = difficultyLevels.map(d => `
    <div class="row">
      <div class="row-main">
        <div class="row-title">
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${escAttr(d.color)};margin-right:8px"></span>
          ${escHtml(d.title)}
        </div>
        <div class="row-meta"><span>${escHtml(d.text)}</span></div>
      </div>
      <div class="row-actions">
        <button class="btn btn-ghost btn-sm" onclick="openDifficultyForm('${d.code}')">Редактировать</button>
      </div>
    </div>`).join('');
}

function openDifficultyForm(code) {
  const d = difficultyLevels.find(x => x.code === code);
  if (!d) return;
  showModal(`Сложность: ${d.title}`, `
    <div class="field"><label>Подпись</label>
      <input id="df-title" value="${escAttr(d.title)}"></div>
    <div class="field"><label>Пояснение</label>
      <textarea id="df-text" rows="4">${escHtml(d.text)}</textarea>
      <div class="hint">Текст в подсказке «что означают уровни сложности».</div></div>
    <div class="field"><label>Цвет</label>
      <input id="df-color" type="color" value="${escAttr(d.color)}" style="width:70px;height:38px;padding:2px">
      <div class="hint">Им красятся точки-индикатор и сама подпись уровня.</div></div>
  `, async () => {
    const payload = {
      title: document.getElementById('df-title').value.trim(),
      text: document.getElementById('df-text').value.trim(),
      color: document.getElementById('df-color').value,
    };
    if (!payload.title || !payload.text) { toast('Подпись и пояснение обязательны', true); return; }
    const saved = await api('PATCH', `/difficulty-levels/${code}`, payload);
    Object.assign(d, saved);
    renderDifficultyList();
    closeModal();
    toast('Сохранено');
  });
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
  const [cats, tr, cps, arts, tags, scs, mgs, fqs, pgs, diffs, dsts] = await Promise.all([
    api('GET', '/categories'),
    api('GET', '/trails'),
    api('GET', '/checkpoints'),
    api('GET', '/articles'),
    api('GET', '/equipment-tags'),
    api('GET', '/scenarios'),
    api('GET', '/magnets'),
    api('GET', '/faq-sets'),
    api('GET', '/site-pages'),
    api('GET', '/difficulty-levels'),
    api('GET', '/districts'),
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
  difficultyLevels = diffs || [];
  districts = dsts || [];
  refreshDistrictOpts();

  renderArticles();
  renderRoutes();
  renderPlaces();
  renderScenarios();
  renderBlocks();
  renderSitePages();
  renderDifficultyList();
  renderDistricts();
}

loadAll();
