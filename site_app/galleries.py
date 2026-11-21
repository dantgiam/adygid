"""Галереи в тексте статей, описаний и сценариев.

На рендере, без правки сохранённого HTML. Повторный прогон даёт тот же
результат: исходник в базе не нужен и не переписывается.

Два способа, которыми фото попадают в текст, раньше выглядели по-разному.

Редактор (Quill) кладёт кадры в один абзац: ``<p><img alt="подпись">``.
Несколько кадров подряд становились лентой, где ширина каждого кадра
считалась из его собственных пропорций. Панорама растягивалась на весь
экран, портрет сжимался в узкую полоску, и ряд не стоял по центру колонки.

Новые статьи (вёрстка ``<figure class="shot">``) этого пути не проходят:
у класса нет стилей, и браузер оставляет у ``figure`` свои поля по 40px.
Плюс снимки с Commons приезжают какими угодно: лента 6:1 и портрет 2:3
стоят в тексте рядом с ровными старыми кадрами 3:2 и выглядят сломанными.
Старые кадры почти все 3:2, поэтому та же дырка в стилях на них не бросалась
в глаза.

Здесь оба варианта собираются в одну галерею, как в Т—Ж: один кадр на
ширину колонки, общая горизонтальная рамка 3:2, фото по центру рамки.
Старые снимки 3:2 заполняют её целиком. Портрет и панорама больше не
ломают колонку: рамка одна и та же, лишнее обрезается от центра, а не
от левого края. Это не прежняя обрезка всего подряд под вертикальные
3:4. Подпись, счётчик, ленивая загрузка и зарезервированная высота на
месте. Несколько кадров подряд листаются свайпом и стрелками.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape, unescape
from html.parser import HTMLParser

# 3:2 — пропорция почти всех старых фото на сайте. Рамка этой высоты
# не меняет их вид, а панораму и портрет ставит в тот же прямоугольник.
FRAME_W = 1500
FRAME_H = 1000

_BLOCK_RE = re.compile(
    r'<figure\b[^>]*\bclass\s*=\s*"([^"]*)"[^>]*>(.*?)</figure>'
    r'|<p\b[^>]*>((?:\s*(?:<img\b[^>]*>|&nbsp;|<br\s*/?>))+)\s*</p>',
    re.IGNORECASE | re.DOTALL,
)
_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(
    r"""\b([A-Za-z_:][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""",
)
_FIGCAPTION_RE = re.compile(r"<figcaption\b[^>]*>(.*?)</figcaption>", re.IGNORECASE | re.DOTALL)
_SMALL_RE = re.compile(r"<small\b[^>]*>(.*?)</small>", re.IGNORECASE | re.DOTALL)
_TEXT_SPAN_RE = re.compile(
    r'<span\b[^>]*\bclass\s*=\s*"[^"]*\barticle-gallery-text\b[^"]*"[^>]*>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
# Между соседними фото можно склеивать только пустоту: пробелы, пустой
# абзац Quill и &nbsp;. Живой текст разрывает группу — кадр остаётся
# у своего абзаца.
_GAP_RE = re.compile(
    r"(?:\s|&nbsp;|<p\b[^>]*>\s*(?:&nbsp;|<br\s*/?>|\s)*</p>)*",
    re.IGNORECASE,
)
_PHOTO_CLASSES = frozenset({"shot", "article-figure"})

_PREV_SVG = (
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" fill="none" '
    'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_NEXT_SVG = (
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" fill="none" '
    'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


@dataclass
class _Photo:
    src: str
    caption: str
    credit: str  # уже очищенный HTML, можно вставлять как есть


class _CreditSanitizer(HTMLParser):
    """Оставляем текст, ссылки http(s) и простое выделение. Скрипты и
    javascript:-ссылки из подписи автора не проходят."""

    _INLINE = frozenset({"em", "strong", "b", "i"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._open_a = 0
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in ("script", "style"):
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        if tag in self._INLINE:
            self.parts.append(f"<{tag}>")
            return
        if tag != "a":
            return
        href = ""
        for key, value in attrs:
            if key.lower() == "href" and value:
                href = value.strip()
        if _safe_href(href):
            self.parts.append(
                f'<a href="{escape(href, quote=True)}" rel="nofollow noopener" target="_blank">'
            )
            self._open_a += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag in self._INLINE:
            self.parts.append(f"</{tag}>")
        elif tag == "a" and self._open_a:
            self.parts.append("</a>")
            self._open_a -= 1

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        self.parts.append(escape(re.sub(r"\s+", " ", data)))

    def result(self) -> str:
        return "".join(self.parts).strip()


def _safe_href(href: str) -> bool:
    low = href.lower()
    if any(mark in low for mark in ("javascript:", "data:", "vbscript:")):
        return False
    return low.startswith(("https://", "http://", "/", "mailto:"))


def _safe_src(src: str) -> bool:
    low = src.lower()
    if not src or any(mark in low for mark in ("javascript:", "data:", "vbscript:")):
        return False
    return low.startswith(("https://", "http://", "/"))


def _sanitize_credit(fragment: str) -> str:
    parser = _CreditSanitizer()
    parser.feed(fragment or "")
    parser.close()
    return parser.result()


def _plain(fragment: str) -> str:
    return " ".join(unescape(_TAG_RE.sub(" ", fragment or "")).split())


def _attrs(tag: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _ATTR_RE.finditer(tag):
        value = match.group(2) if match.group(2) is not None else match.group(3) or ""
        out[match.group(1).lower()] = unescape(value)
    return out


def _caption_and_credit(inner: str) -> tuple[str, str]:
    cap = _FIGCAPTION_RE.search(inner)
    if not cap:
        return "", ""
    raw = cap.group(1)
    span = _TEXT_SPAN_RE.search(raw)
    small = _SMALL_RE.search(raw)
    if span:
        caption = _plain(span.group(1))
    else:
        before = raw[: small.start()] if small else raw
        caption = _plain(before)
    credit = _sanitize_credit(small.group(1)) if small else ""
    return caption, credit


def _photos_from_imgs(tags: list[str], caption: str = "", credit: str = "") -> list[_Photo]:
    photos: list[_Photo] = []
    for tag in tags:
        attrs = _attrs(tag)
        src = attrs.get("src", "").strip()
        if not _safe_src(src):
            continue
        alt = _plain(attrs.get("alt", ""))
        photos.append(_Photo(src=src, caption=caption or alt, credit=credit))
    return photos


def _photos_from_match(match: re.Match[str]) -> list[_Photo] | None:
    """None — это не фотоблок, его надо оставить как был."""
    classes = match.group(1)
    if classes is not None:
        tokens = set(classes.split())
        if not (tokens & _PHOTO_CLASSES):
            return None
        caption, credit = _caption_and_credit(match.group(2))
        photos = _photos_from_imgs(_IMG_RE.findall(match.group(2)), caption, credit)
        return photos or None
    photos = _photos_from_imgs(_IMG_RE.findall(match.group(3) or ""))
    return photos or None


def _img(photo: _Photo) -> str:
    return (
        f'<img src="{escape(photo.src, quote=True)}" alt="{escape(photo.caption, quote=True)}" '
        f'width="{FRAME_W}" height="{FRAME_H}" loading="lazy" decoding="async">'
    )


def _credit_html(photo: _Photo) -> str:
    if not photo.credit:
        return ""
    return f'<small class="article-gallery-credit">{photo.credit}</small>'


def _single(photo: _Photo) -> str:
    caption = ""
    if photo.caption or photo.credit:
        text = (
            f'<span class="article-gallery-text">{escape(photo.caption)}</span>'
            if photo.caption else ""
        )
        caption = f"<figcaption>{text}{_credit_html(photo)}</figcaption>"
    return (
        '<figure class="article-figure">'
        f'<div class="article-frame">{_img(photo)}</div>'
        f"{caption}</figure>"
    )


def _carousel(photos: list[_Photo]) -> str:
    total = len(photos)
    items: list[str] = []
    for index, photo in enumerate(photos, start=1):
        text = (
            f'<span class="article-gallery-text">{escape(photo.caption)}</span>'
            if photo.caption else ""
        )
        items.append(
            '<figure class="article-gallery-item">'
            f'<div class="article-frame">{_img(photo)}</div>'
            '<figcaption class="article-gallery-caption">'
            f'<span class="article-gallery-counter">{index} / {total}</span>'
            f"{text}{_credit_html(photo)}</figcaption></figure>"
        )
    nav = (
        '<div class="article-gallery-arrows">'
        '<button type="button" class="gal-nav gal-prev" data-gal-prev disabled aria-label="Предыдущее фото">'
        f"{_PREV_SVG}</button>"
        '<button type="button" class="gal-nav gal-next" data-gal-next aria-label="Следующее фото">'
        f"{_NEXT_SVG}</button></div>"
    )
    return (
        '<div class="article-gallery" data-gallery tabindex="0" role="region" '
        'aria-roledescription="карусель" aria-label="Фотографии">'
        '<div class="article-gallery-stage">'
        f'<div class="article-gallery-track" data-gal-track>{"".join(items)}</div>'
        f"{nav}</div></div>"
    )


def _render_photos(photos: list[_Photo]) -> str:
    if len(photos) == 1:
        return _single(photos[0])
    return _carousel(photos)


def render_article_gallery(html: str) -> str:
    if not html:
        return html or ""
    matches = list(_BLOCK_RE.finditer(html))
    if not matches:
        return html

    parts: list[str] = []
    pos = 0
    index = 0
    while index < len(matches):
        match = matches[index]
        photos = _photos_from_match(match)
        if not photos:
            parts.append(html[pos:match.end()])
            pos = match.end()
            index += 1
            continue

        group = [photos]
        end = match.end()
        nxt = index + 1
        while nxt < len(matches):
            follower = matches[nxt]
            between = html[end:follower.start()]
            follower_photos = _photos_from_match(follower)
            if not follower_photos or _GAP_RE.fullmatch(between) is None:
                break
            group.append(follower_photos)
            end = follower.end()
            nxt += 1

        flat = [photo for chunk in group for photo in chunk]
        parts.append(html[pos:match.start()])
        # Одинокое фото без подписи в обычном абзаце так и остаётся вставкой
        # на всю ширину — так оно жило в старых статьях. Фигура shot даже
        # без подписи идёт в рамку: иначе браузерные поля figure никуда не
        # деваются.
        bare_paragraph = match.group(1) is None and nxt == index + 1
        if bare_paragraph and len(flat) == 1 and not flat[0].caption and not flat[0].credit:
            parts.append(match.group(0))
        else:
            parts.append(_render_photos(flat))
        pos = end
        index = nxt

    parts.append(html[pos:])
    return "".join(parts)
