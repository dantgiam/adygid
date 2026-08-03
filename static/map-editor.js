/* ═══════════════════════════════════════════════════════════════
   VectorEditor — рисование и правка линий на карте «как в Фигме».

   Почему свой инструмент, а не leaflet-draw: leaflet-draw умеет только
   поставить линию и всё — потом её нельзя ни подвинуть, ни вставить точку
   в середину, а перерисовка на каждое движение мыши идёт через DOM-слой и
   на длинной тропе заметно тормозит.

   Здесь:
     • линии рисуются в canvas-слое (один перерисовываемый холст, а не
       сотни DOM-узлов), резинка за курсором обновляется по кадрам экрана;
     • у выбранной линии видны квадратные якоря — их таскают мышью,
       а между ними висят полупрозрачные «серединки»: потянул за неё —
       родился новый якорь ровно там, где потянул;
     • перо липнет к чужим якорям и к точкам маршрута (SNAP_PX), поэтому
       участки стыкуются без щелей;
     • Shift держит угол кратным 15°, Backspace снимает последний якорь,
       Enter/двойной клик заканчивают линию, Esc отменяет.

   Наружу отдаются только готовые координаты — что с ними делать
   (какой запрос слать) решает admin.js.
   ═══════════════════════════════════════════════════════════════ */

(function (global) {
  'use strict';

  const SNAP_PX = 12;          // радиус прилипания к чужому якорю, пиксели экрана
  const ANGLE_STEP = 15;       // шаг угла при зажатом Shift, градусы
  const DEDUPE_PX = 3;         // ближе этого два клика считаем одним (двойной клик)

  // ── Геометрия ────────────────────────────────────────────────
  function toRad(d) { return d * Math.PI / 180; }

  function distMeters(a, b) {
    const R = 6371000;
    const dLat = toRad(b.lat - a.lat);
    const dLon = toRad(b.lng - a.lng);
    const s = Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(s));
  }

  function pathLength(pts) {
    let sum = 0;
    for (let i = 1; i < pts.length; i++) sum += distMeters(pts[i - 1], pts[i]);
    return sum;
  }

  function handleIcon(extraClass) {
    return L.divIcon({
      className: 'vec-handle-wrap',
      html: `<i class="vec-handle ${extraClass || ''}"></i>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    });
  }

  class VectorEditor {
    constructor(map, opts) {
      this.map = map;
      this.opts = opts || {};

      // Один холст на все линии: перерисовка идёт кадром целиком и не
      // упирается в количество узлов, как DOM-слой.
      this.renderer = L.canvas({ padding: 0.6 }).addTo(map);
      this.overlay = L.canvas({ padding: 0.6 }).addTo(map);

      this.lines = new Map();      // id → { data, poly }
      this.selectedId = null;
      this.handles = [];           // маркеры-якоря выбранной линии
      this.draft = null;           // текущий сеанс рисования
      this.snapTargets = [];       // [L.LatLng] — куда липнет перо
      this.snapMark = null;
      this._raf = null;

      this._onMapClick = this._onMapClick.bind(this);
      this._onMapMove = this._onMapMove.bind(this);
      this._onMapDblClick = this._onMapDblClick.bind(this);
      this._onKey = this._onKey.bind(this);

      map.on('click', this._onMapClick);
    }

    // ── Отрисовка существующих линий ───────────────────────────
    setLines(list) {
      const seen = new Set();
      list.forEach(item => {
        seen.add(item.id);
        const existing = this.lines.get(item.id);
        if (existing) {
          existing.data = item;
          existing.poly.setLatLngs(item.latlngs);
          existing.poly.setStyle({ color: item.color, weight: item.weight || 5 });
        } else {
          const poly = L.polyline(item.latlngs, {
            renderer: this.renderer,
            color: item.color,
            weight: item.weight || 5,
            interactive: !this.draft,
            bubblingMouseEvents: false,
          }).addTo(this.map);
          poly.on('click', (e) => {
            L.DomEvent.stop(e);
            if (this.draft) return;          // во время рисования клик по линии — обычный клик
            this.select(item.id);
          });
          this.lines.set(item.id, { data: item, poly });
        }
      });

      // Линии, которых больше нет в данных (удалили участок).
      Array.from(this.lines.keys()).forEach(id => {
        if (seen.has(id)) return;
        this.map.removeLayer(this.lines.get(id).poly);
        this.lines.delete(id);
        if (this.selectedId === id) this.selectedId = null;
      });

      if (this.selectedId && this.lines.has(this.selectedId)) this._buildHandles();
      else this._clearHandles();
    }

    setSnapTargets(latlngs) {
      this.snapTargets = latlngs || [];
    }

    // ── Выделение линии и её якоря ─────────────────────────────
    select(id) {
      if (this.selectedId === id) return;
      this.selectedId = id;
      this._buildHandles();
      this._emitSelect();
    }

    deselect() {
      if (this.selectedId === null) return;
      this.selectedId = null;
      this._clearHandles();
      this._emitSelect();
    }

    _emitSelect() {
      if (this.opts.onSelect) this.opts.onSelect(this.selectedId);
    }

    _clearHandles() {
      this.handles.forEach(m => this.map.removeLayer(m));
      this.handles = [];
    }

    _buildHandles() {
      this._clearHandles();
      const line = this.lines.get(this.selectedId);
      if (!line) return;
      const pts = line.poly.getLatLngs();

      // Якоря: тянем — двигается вершина, Alt/правый клик — вершина исчезает.
      pts.forEach((ll, i) => {
        const m = L.marker(ll, {
          icon: handleIcon(''),
          draggable: true,
          keyboard: false,
          zIndexOffset: 600,
        }).addTo(this.map);

        m.on('drag', () => {
          const cur = line.poly.getLatLngs();
          cur[i] = m.getLatLng();
          line.poly.setLatLngs(cur);
          this._syncMidHandles(cur);
        });
        m.on('dragend', () => this._commitSelected());
        m.on('click', (e) => {
          L.DomEvent.stop(e);
          if (e.originalEvent.altKey) this._removeVertex(i);
        });
        m.on('contextmenu', (e) => {
          L.DomEvent.stop(e);
          this._removeVertex(i);
        });
        m._vecIndex = i;
        m._vecMid = false;
        this.handles.push(m);
      });

      // Серединки: потянул — на этом месте появился новый якорь.
      for (let i = 0; i < pts.length - 1; i++) {
        const mid = L.latLng((pts[i].lat + pts[i + 1].lat) / 2, (pts[i].lng + pts[i + 1].lng) / 2);
        const m = L.marker(mid, {
          icon: handleIcon('mid'),
          draggable: true,
          keyboard: false,
          zIndexOffset: 500,
          opacity: 1,
        }).addTo(this.map);

        let bornIndex = null;
        const born = () => {
          if (bornIndex !== null) return;
          const cur = line.poly.getLatLngs();
          bornIndex = m._vecIndex + 1;
          cur.splice(bornIndex, 0, m.getLatLng());
          line.poly.setLatLngs(cur);
          m.getElement().querySelector('.vec-handle').classList.remove('mid');
        };
        m.on('dragstart', born);
        m.on('drag', () => {
          born();
          const cur = line.poly.getLatLngs();
          cur[bornIndex] = m.getLatLng();
          line.poly.setLatLngs(cur);
        });
        m.on('dragend', () => this._commitSelected());
        m.on('click', (e) => {
          // Клик без перетаскивания — тоже способ добавить якорь.
          L.DomEvent.stop(e);
          born();
          this._commitSelected();
        });
        m._vecIndex = i;
        m._vecMid = true;
        this.handles.push(m);
      }
    }

    _syncMidHandles(pts) {
      this.handles.forEach(m => {
        if (!m._vecMid) return;
        const i = m._vecIndex;
        if (!pts[i] || !pts[i + 1]) return;
        m.setLatLng(L.latLng((pts[i].lat + pts[i + 1].lat) / 2, (pts[i].lng + pts[i + 1].lng) / 2));
      });
    }

    _removeVertex(i) {
      const line = this.lines.get(this.selectedId);
      if (!line) return;
      const pts = line.poly.getLatLngs();
      if (pts.length <= 2) {
        if (this.opts.onMessage) this.opts.onMessage('В линии должно остаться хотя бы две точки');
        return;
      }
      pts.splice(i, 1);
      line.poly.setLatLngs(pts);
      this._commitSelected();
    }

    _commitSelected() {
      const line = this.lines.get(this.selectedId);
      if (!line) return;
      const pts = line.poly.getLatLngs().map(ll => L.latLng(ll.lat, ll.lng));
      this._buildHandles();
      if (this.opts.onUpdate) this.opts.onUpdate(this.selectedId, pts);
    }

    // ── Перо ───────────────────────────────────────────────────
    get drawing() { return !!this.draft; }

    startDraw(options) {
      this.cancelDraw();
      this.deselect();
      const color = (options && options.color) || '#278C3E';

      this.draft = {
        pts: [],
        color,
        extendId: null,        // дорисовываем существующий участок…
        prepend: false,        // …с начала или с конца
        poly: L.polyline([], { renderer: this.overlay, color, weight: 5, interactive: false }).addTo(this.map),
        rubber: L.polyline([], {
          renderer: this.overlay, color, weight: 2, opacity: .9,
          dashArray: '5,6', interactive: false,
        }).addTo(this.map),
        dots: L.layerGroup().addTo(this.map),
      };

      // Пока рисуем, готовые линии не ловят клики — иначе клик, попавший на
      // уже нарисованный участок, выделял бы его вместо постановки якоря.
      this.lines.forEach(l => { l.poly.options.interactive = false; });

      this.map.doubleClickZoom.disable();
      L.DomUtil.addClass(this.map.getContainer(), 'vec-drawing');
      this.map.on('mousemove', this._onMapMove);
      this.map.on('dblclick', this._onMapDblClick);
      document.addEventListener('keydown', this._onKey);
      this._emitDraft();
    }

    cancelDraw() {
      if (!this.draft) return;
      this._teardownDraft();
      this._emitDraft();
    }

    finishDraw() {
      if (!this.draft) return;
      const d = this.draft;
      const pts = d.pts.slice();
      const extendId = d.extendId;
      const prepend = d.prepend;
      this._teardownDraft();
      this._emitDraft();

      if (extendId !== null && this.lines.has(extendId)) {
        // Продолжение участка: первый узел черновика — это сам конец линии,
        // его выбрасываем, иначе в геометрии окажется точка-двойник.
        const base = this.lines.get(extendId).poly.getLatLngs().map(ll => L.latLng(ll.lat, ll.lng));
        const tail = pts.slice(1);
        if (!tail.length) return;
        const merged = prepend ? tail.reverse().concat(base) : base.concat(tail);
        if (this.opts.onUpdate) this.opts.onUpdate(extendId, merged);
        return;
      }
      if (pts.length >= 2 && this.opts.onCreate) this.opts.onCreate(pts);
    }

    _teardownDraft() {
      const d = this.draft;
      this.draft = null;
      this.lines.forEach(l => { l.poly.options.interactive = true; });
      if (d) {
        this.map.removeLayer(d.poly);
        this.map.removeLayer(d.rubber);
        this.map.removeLayer(d.dots);
      }
      if (this.snapMark) { this.map.removeLayer(this.snapMark); this.snapMark = null; }
      this.map.off('mousemove', this._onMapMove);
      this.map.off('dblclick', this._onMapDblClick);
      document.removeEventListener('keydown', this._onKey);
      L.DomUtil.removeClass(this.map.getContainer(), 'vec-drawing');
      this.map.doubleClickZoom.enable();
      if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; }
    }

    _emitDraft() {
      if (!this.opts.onDraft) return;
      this.opts.onDraft(this.draft
        ? { count: this.draft.pts.length, length: pathLength(this.draft.pts), extending: this.draft.extendId !== null }
        : null);
    }

    // ── События карты ──────────────────────────────────────────
    _onMapClick(e) {
      if (!this.draft) {
        this.deselect();
        return;
      }
      const target = this._resolvePoint(e.latlng, e.originalEvent);

      // Клик в ту же точку — это второй клик двойного, его не считаем.
      const last = this.draft.pts[this.draft.pts.length - 1];
      if (last && this._pixelDist(last, target.latlng) < DEDUPE_PX) return;

      // Первый клик по концу существующего участка — продолжаем его.
      if (!this.draft.pts.length && target.endpoint) {
        this.draft.extendId = target.endpoint.id;
        this.draft.prepend = target.endpoint.atStart;
      }

      this.draft.pts.push(target.latlng);
      this.draft.poly.setLatLngs(this.draft.pts);
      L.circleMarker(target.latlng, {
        renderer: this.overlay, radius: 3.5, color: '#fff', weight: 1.5,
        fillColor: this.draft.color, fillOpacity: 1, interactive: false,
      }).addTo(this.draft.dots);
      this._emitDraft();
    }

    _onMapDblClick(e) {
      L.DomEvent.stop(e);
      this.finishDraw();
    }

    _onMapMove(e) {
      this._cursor = e.latlng;
      this._shift = e.originalEvent.shiftKey;
      if (this._raf) return;
      this._raf = requestAnimationFrame(() => {
        this._raf = null;
        this._updateRubber();
      });
    }

    _updateRubber() {
      if (!this.draft || !this._cursor) return;
      const target = this._resolvePoint(this._cursor, { shiftKey: this._shift });
      const last = this.draft.pts[this.draft.pts.length - 1];
      this.draft.rubber.setLatLngs(last ? [last, target.latlng] : []);

      // Кружок подсветки там, где перо прилипло к чужому якорю.
      if (target.snapped) {
        if (!this.snapMark) {
          this.snapMark = L.circleMarker(target.latlng, {
            renderer: this.overlay, radius: 7, color: '#D6A324', weight: 2,
            fillColor: '#D6A324', fillOpacity: .25, interactive: false,
          }).addTo(this.map);
        } else {
          this.snapMark.setLatLng(target.latlng);
        }
      } else if (this.snapMark) {
        this.map.removeLayer(this.snapMark);
        this.snapMark = null;
      }

      if (this.opts.onDraft && last) {
        this.opts.onDraft({
          count: this.draft.pts.length,
          length: pathLength(this.draft.pts) + distMeters(last, target.latlng),
          extending: this.draft.extendId !== null,
          preview: true,
        });
      }
    }

    _onKey(e) {
      if (!this.draft) return;
      if (e.key === 'Escape') {
        L.DomEvent.stop(e);
        this.cancelDraw();
      } else if (e.key === 'Enter') {
        L.DomEvent.stop(e);
        this.finishDraw();
      } else if (e.key === 'Backspace' || (e.key.toLowerCase() === 'z' && (e.ctrlKey || e.metaKey))) {
        L.DomEvent.stop(e);
        this.draft.pts.pop();
        this.draft.poly.setLatLngs(this.draft.pts);
        const dots = this.draft.dots.getLayers();
        if (dots.length) this.draft.dots.removeLayer(dots[dots.length - 1]);
        this.draft.rubber.setLatLngs([]);
        this._emitDraft();
      }
    }

    // ── Прилипание и угол ──────────────────────────────────────
    _pixelDist(a, b) {
      return this.map.latLngToContainerPoint(a).distanceTo(this.map.latLngToContainerPoint(b));
    }

    /** Куда на самом деле встанет точка: с учётом прилипания и Shift. */
    _resolvePoint(latlng, ev) {
      const cursorPt = this.map.latLngToContainerPoint(latlng);

      // 1. Прилипание к концам существующих линий — так стыкуются участки.
      let best = null;
      this.lines.forEach((line, id) => {
        const pts = line.poly.getLatLngs();
        if (!pts.length) return;
        [[pts[0], true], [pts[pts.length - 1], false]].forEach(([ll, atStart]) => {
          const d = this.map.latLngToContainerPoint(ll).distanceTo(cursorPt);
          if (d < SNAP_PX && (!best || d < best.d)) best = { d, latlng: ll, endpoint: { id, atStart } };
        });
      });

      // 2. Прилипание к точкам маршрута и прочим целям.
      this.snapTargets.forEach(ll => {
        const d = this.map.latLngToContainerPoint(ll).distanceTo(cursorPt);
        if (d < SNAP_PX && (!best || d < best.d)) best = { d, latlng: ll, endpoint: null };
      });

      if (best) return { latlng: L.latLng(best.latlng.lat, best.latlng.lng), snapped: true, endpoint: best.endpoint };

      // 3. Shift — держим угол кратным ANGLE_STEP от последнего якоря.
      const last = this.draft && this.draft.pts[this.draft.pts.length - 1];
      if (ev && ev.shiftKey && last) {
        const lastPt = this.map.latLngToContainerPoint(last);
        const dx = cursorPt.x - lastPt.x, dy = cursorPt.y - lastPt.y;
        const len = Math.sqrt(dx * dx + dy * dy);
        const step = toRad(ANGLE_STEP);
        const angle = Math.round(Math.atan2(dy, dx) / step) * step;
        const snapped = L.point(lastPt.x + Math.cos(angle) * len, lastPt.y + Math.sin(angle) * len);
        return { latlng: this.map.containerPointToLatLng(snapped), snapped: false, endpoint: null };
      }

      return { latlng, snapped: false, endpoint: null };
    }

    destroy() {
      this.cancelDraw();
      this._clearHandles();
      this.lines.forEach(l => this.map.removeLayer(l.poly));
      this.lines.clear();
      this.map.off('click', this._onMapClick);
    }
  }

  global.VectorEditor = VectorEditor;
  global.vecPathLength = pathLength;
})(window);
