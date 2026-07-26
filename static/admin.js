/* ═══════════════════════════════════════════════════════════════
   АдыГид — админка.

   Три раздела (статьи / маршруты / места) живут как отдельные «экраны»:
   в один момент времени виден ровно один .view. Карта открывается только
   когда она реально нужна (правка геометрии маршрута или установка точки),
   а не висит фоном под всеми формами.
   ═══════════════════════════════════════════════════════════════ */

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

// ── Вкладки / экраны ───────────────────────────────────────────
// Подэкраны (редактор статьи, карта) — не отдельные вкладки: подсвечиваем
// раздел, из которого пришли, чтобы не терялась ориентация.
const TAB_OF_VIEW = {
  'article-editor': 'articles',
  'route-map': 'routes',
  'place-map': 'places',
};

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

// ── Редактор описания внутри модалки (маршрут / место) ─────────
// Тот же принцип, что и в статьях: пишем как видим, без ручного HTML.
function descEditorHtml(label) {
  return `<div class="field">
    <label>${label}</label>
    <div class="hint" style="margin:0 0 6px">Выделите текст, чтобы сделать заголовок, список или ссылку.</div>
    <div class="desc-editor-wrap"><div id="desc-editor"></div></div>
  </div>`;
}

function initDescEditor(html) {
  descQuill = new Quill('#desc-editor', {
    theme: 'bubble',
    placeholder: 'Описание — что это за место, как добраться, что учесть...',
    modules: {
      toolbar: [
        ['bold', 'italic', 'link'],
        [{ header: 2 }, { header: 3 }],
        [{ list: 'ordered' }, { list: 'bullet' }],
      ],
    },
  });
  descQuill.setContents([], 'silent');
  if (html) descQuill.clipboard.dangerouslyPasteHTML(0, html, 'silent');
}

function readDescEditor() {
  if (!descQuill) return null;
  const html = descQuill.root.innerHTML.trim();
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

function setArticleBody(html) {
  // Только через clipboard-парсер Quill: прямое присваивание root.innerHTML
  // редактор не разбирает в свою модель, и часть разметки (списки в первую
  // очередь) молча теряется при первом же сохранении.
  articleQuill.setContents([], 'silent');
  if (html) articleQuill.clipboard.dangerouslyPasteHTML(0, html, 'silent');
}

function initArticleQuill() {
  if (articleQuill) return;
  articleQuill = new Quill('#article-editor', {
    theme: 'bubble',
    placeholder: 'Текст статьи. Выделите фрагмент, чтобы отформатировать.',
    modules: {
      toolbar: [
        ['bold', 'italic', 'underline', 'link'],
        [{ header: 2 }, { header: 3 }],
        [{ list: 'ordered' }, { list: 'bullet' }],
        ['blockquote'],
      ],
    },
  });
  articleQuill.on('text-change', scheduleAutosave);
}

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

function setSaveState(text, saved) {
  const el = document.getElementById('save-state');
  el.textContent = text;
  el.classList.toggle('saved', !!saved);
}

// ── Автосохранение черновика в localStorage ────────────────────
function collectArticleDraft() {
  return {
    savedAt: Date.now(),
    title: document.getElementById('a-title').value,
    excerpt: document.getElementById('a-excerpt').value,
    slug: document.getElementById('a-slug').value,
    cover_url: document.getElementById('a-cover-url').value,
    district: document.getElementById('a-district').value,
    is_published: document.getElementById('a-published').checked,
    body: articleQuill ? articleQuill.root.innerHTML : '',
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
    articleQuill ? articleQuill.root.innerHTML : '',
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
    body: articleQuill.root.innerHTML,
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

async function insertPhoto() { await photoFlow(false); }
async function insertCollage() { await photoFlow(true); }

async function photoFlow(multiple) {
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

  showModal(multiple ? 'Коллаж' : 'Фото', `<div class="pickfile">${rows}</div>`, async () => {
    const caps = Array.from(document.querySelectorAll('.cap-input')).map(el => el.value.trim());
    document.getElementById('modal-save').disabled = true;
    document.getElementById('modal-save').textContent = 'Загружаю...';

    const uploaded = [];
    for (let i = 0; i < chosen.length; i++) {
      const up = await uploadFile(chosen[i]);
      if (up) uploaded.push({ url: up.url, caption: caps[i] || '' });
    }
    document.getElementById('modal-save').disabled = false;

    if (uploaded.length) {
      let index = articleQuill.getSelection(true).index;
      uploaded.forEach(item => {
        articleQuill.insertEmbed(index, 'image', item.url, 'user');
        // Quill не умеет alt из коробки — проставляем прямо в DOM редактора,
        // при сохранении он уедет вместе с картинкой (сайт делает из alt подпись).
        const imgs = articleQuill.root.querySelectorAll(`img[src="${CSS.escape(item.url)}"]`);
        const el = imgs[imgs.length - 1];
        if (el) { el.alt = item.caption; el.title = item.caption; }
        index += 1;
      });
      articleQuill.insertText(index, '\n', 'user');
      articleQuill.setSelection(index + 1);
      scheduleAutosave();
    }
    closeModal();
  }, { saveLabel: 'Вставить' });
}

function insertInternalLink() {
  const places = checkpoints.filter(c => c.show_as_place);
  const rows = [
    ...places.map(p => ({ url: `/mesta/${p.id}`, label: p.name, kind: 'Место' })),
    ...trails.map(t => ({ url: `/marshruty/${t.id}`, label: t.name, kind: 'Маршрут' })),
  ];
  if (!rows.length) { toast('Сначала добавьте места или маршруты', true); return; }

  showModal('Ссылка на место или маршрут', `
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
    const range = articleQuill.getSelection(true);
    if (range.length > 0) {
      articleQuill.format('link', picked.value, 'user');
    } else {
      const label = picked.dataset.label;
      articleQuill.insertText(range.index, label, { link: picked.value }, 'user');
      articleQuill.setSelection(range.index + label.length);
    }
    scheduleAutosave();
    closeModal();
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

function openRouteForm(id) {
  const t = id ? trails.find(x => x.id === id) : null;
  const v = t || {};
  showModal(t ? 'Маршрут: текст и параметры' : 'Новый маршрут', `
    <div class="field"><label>Название</label>
      <input id="t-name" value="${escAttr(v.name || '')}" placeholder="Водопады Руфабго">
    </div>
    <div class="field-row">
      <div class="field"><label>Категория</label>
        <select id="t-category">${categoryOptionsHtml('trail', v.category_id)}</select>
      </div>
      <div class="field"><label>Длительность (минут)</label>
        <input id="t-duration" type="number" min="0" value="${v.duration_minutes || ''}" placeholder="150">
      </div>
    </div>
    ${descEditorHtml('Описание')}
    ${criteriaHtml(v)}
    ${t ? '<div class="hint" style="margin-top:12px">Тропу и точки по пути редактируйте кнопкой «Карта и точки» в списке маршрутов.</div>' : ''}
  `, async () => {
    const payload = Object.assign({
      name: document.getElementById('t-name').value.trim(),
      category_id: parseInt(document.getElementById('t-category').value, 10) || null,
      duration_minutes: parseInt(document.getElementById('t-duration').value, 10) || null,
      description: readDescEditor(),
    }, readCriteria());
    if (!payload.name) { toast('Введите название', true); return; }
    const saved = t ? await api('PATCH', `/trails/${t.id}`, payload) : await api('POST', '/trails', payload);
    if (saved) {
      await loadAll();
      closeModal();
      toast('Маршрут сохранён');
      if (!t) openRouteMap(saved.id);
    }
  }, {
    wide: true,
    preview: () => openPreview(
      'description',
      readDescEditor() || '',
      document.getElementById('t-name').value.trim(),
      'Маршрут',
    ),
  });
  initDescEditor(v.description || '');
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

// ── Форма точки / места ────────────────────────────────────────
function openPointForm(id, creating) {
  const c = id ? checkpoints.find(x => x.id === id) : null;
  const v = c || {};
  const inTrail = creating ? !!activeTrail : !!(c && c.trail_id);
  const showAsPlace = c ? c.show_as_place : !inTrail;

  const publishExtra = inTrail ? `
    <label class="toggle" style="margin-top:4px">
      <input type="checkbox" id="m-show-place" ${showAsPlace ? 'checked' : ''}>
      <span class="toggle-track"></span>
      <span class="toggle-label">Выделить отдельной точкой
        <small>Точка получит свою страницу и попадёт в раздел «Места». Без этого она видна только внутри маршрута.</small>
      </span>
    </label>` : '';

  showModal(c ? 'Точка маршрута' : 'Новая точка', `
    <div class="field"><label>Название</label>
      <input id="p-name" value="${escAttr(v.name || '')}" placeholder="Водопад Шум">
    </div>
    <div class="field-row">
      <div class="field"><label>Категория</label>
        <select id="p-category">${categoryOptionsHtml('checkpoint', v.category_id)}</select>
      </div>
      <div class="field"><label>Время осмотра (минут)</label>
        <input id="p-duration" type="number" min="0" value="${v.duration_minutes || ''}" placeholder="30">
      </div>
    </div>
    ${descEditorHtml('Описание')}
    ${criteriaHtml(v, { extraPublishHtml: publishExtra })}
  `, async () => {
    const payload = Object.assign({
      name: document.getElementById('p-name').value.trim(),
      category_id: parseInt(document.getElementById('p-category').value, 10) || null,
      duration_minutes: parseInt(document.getElementById('p-duration').value, 10) || null,
      description: readDescEditor(),
    }, readCriteria());

    const toggleEl = document.getElementById('m-show-place');
    if (toggleEl) payload.show_as_place = toggleEl.checked;

    if (!payload.name) { toast('Введите название', true); return; }

    let saved;
    if (c) {
      saved = await api('PATCH', `/checkpoints/${c.id}`, payload);
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

    if (saved) {
      closeModal();
      toast('Сохранено');
      if (activeTrail && document.getElementById('view-route-map').classList.contains('active')) {
        await refreshActiveTrail();
      } else {
        await loadAll();
        renderPlaces();
      }
    }
  }, {
    wide: true,
    preview: () => openPreview(
      'description',
      readDescEditor() || '',
      document.getElementById('p-name').value.trim(),
      'Место',
    ),
  });
  initDescEditor(v.description || '');
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
//  ЗАГРУЗКА ДАННЫХ
// ═══════════════════════════════════════════════════════════════

async function loadAll() {
  const [cats, tr, cps, arts, tags] = await Promise.all([
    api('GET', '/categories'),
    api('GET', '/trails'),
    api('GET', '/checkpoints'),
    api('GET', '/articles'),
    api('GET', '/equipment-tags'),
  ]);
  categories = cats || [];
  trails = tr || [];
  checkpoints = cps || [];
  articles = arts || [];
  equipmentTags = tags || [];

  renderArticles();
  renderRoutes();
  renderPlaces();
}

loadAll();
