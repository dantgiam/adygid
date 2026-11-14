"""Ссылки на карточки мест из текста статей, хабов и районов.

Правило (согласовано 14.11.2026): первое упоминание места, у которого есть
карточка, становится обычной ссылкой в тексте — анкор = само название, как
оно написано в предложении. Не больше одной ссылки на место на странице,
без ссылок на саму страницу, не внутри заголовков, подписей к фото и уже
существующих ссылок, и не больше MAX_PLACE_LINKS разных мест на странице
(считая ссылки, которые уже стояли). Поэтому повторный прогон ничего не
меняет: всё, что можно было связать, уже связано или упёрлось в предел.

Маршруты сюда не входят: их названия описательные («Хаджох за полдня…») и
в тексте почти не встречаются дословно, а угадывать по смыслу — значит
ставить ссылки не туда. Место 50 (Чёртов палец) тоже не связываем: в
текстах это чаще маршрут 11, а не карточка места.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

MAX_PLACE_LINKS = 12

# id карточки → шаблон упоминания. Только однозначные названия; общие
# слова («канатка», «термы», «набережная») не связываем.
_W = r"[а-яё]*"
PLACE_ALIASES: dict[int, str] = {
    24: rf"Хаджохск{_W} теснин{_W}",
    25: rf"Больш{_W} Азишск{_W} пещер{_W}",
    27: rf"[Дд]ольмен{_W} у Гузерипля",
    29: rf"[Оо]зер{_W} Псенодах",
    30: rf"Михайло-Афонск{_W} пустын{_W}",
    36: rf"Хаджохск{_W} карьер{_W}",
    38: rf"Тульск{_W} теснин{_W}",
    40: rf"(?:[Вв]одопад{_W} )?Руфабго",
    41: rf"[Дд]олин{_W} аммонитов",
    42: r"Казач(?:ий|ьего|ьем|ьему|ьим) кам(?:ень|ня|не|нем|ню)",
    44: rf"[Пп]ещер{_W} Сквозн{_W}|Кошач{_W} глаз{_W}",
    45: rf"Беловодь{_W}",
    46: rf"(?:[Гг]ор{_W} )?Физиабго",
    48: rf"Савранск{_W} канатн{_W} дорог{_W}",
    49: rf"[Сс]тар{_W} мост{_W} в Даховской",
    51: rf"Дегуакск{_W} полян{_W}",
    52: rf"Гранитн{_W} каньон{_W}",
    53: rf"[Вв]ерёвочн{_W} парк{_W}",
    55: rf"[Пп]лато Лаго-Наки",
    56: r"Каменн(?:ое|ого|ому|ым) мор(?:е|я|ю|ем)",
    57: rf"Азишск{_W} перевал{_W}",
    58: rf"(?:[Сс]кал{_W} )?Утюг(?![а-яё])",
    59: rf"Мал{_W} Азишск{_W} пещер{_W}",
    60: rf"[Пп]ещер{_W} Нежн{_W}",
    61: rf"(?:[Гг]ор{_W} )?Оштен{_W}",
    62: rf"[Мм]узе{_W} природы(?: Кавказского заповедника)?",
    63: rf"[Вв]ольерн{_W} комплекс{_W}(?: в Гузерипле)?|[Вв]ольер{_W}(?: в Гузерипле)?",
    64: rf"Яворов{_W} полян{_W}",
    65: rf"Партизанск{_W} полян{_W}",
    66: rf"[Пп]рию{_W} Фишт",
    67: r"«АкваТермо»|АкваТермо",
    68: rf"«Кедров{_W} бор{_W}»|Кедров{_W} бор{_W}",
    69: rf"Национальн{_W} музе{_W}(?: Республики Адыгея)?",
    70: rf"Соборн{_W} мечет{_W}",
    72: rf"Псыгупс{_W}",
    73: rf"[Уу]щель{_W} Аминовки",
    74: rf"«Крыл{_W} Ангела»|Крыл{_W} Ангела",
    75: rf"Сахрайск{_W} водопад{_W}",
    76: rf"[Мм]узе{_W} Востока",
    77: rf"[Кк]артинн{_W} галере{_W}",
    78: rf"Мэздах{_W}",
    79: rf"[Дд]ендропарк{_W}(?: имени Букреева| в Гончарке)?",
    80: rf"[Мм]узе{_W} адыгейского чая",
    81: rf"Хаджохск{_W} дольмен{_W}",
    82: rf"[Вв]одопад{_W} Больш{_W} Хаджох",
    83: rf"[Лл]итературн{_W} музе{_W}",
    84: rf"[Гг]ор{_W} Монах",
    85: rf"Богатырск{_W} полян{_W}",
    86: r"«Мамонтий»",
    87: rf"крепост{_W} Меот|[Ии]звестков{_W} печ{_W}",
    88: rf"[Пп]ещер{_W} Желаний",
    89: rf"[Гг]рот{_W} Череп",
    90: rf"[Кк]аньон{_W} (?:реки )?Фарс",
    91: rf"[Сс]кал{_W} Молоток|Окн{_W} в Европу",
    92: rf"Даховск{_W} пещер{_W}",
    94: rf"[Сс]кал{_W} Раскол|[Вв]одопад{_W} Бзыхи",
    99: rf"[Вв]одопад{_W} на Майкопке",
    102: rf"[Гг]ор{_W} Казачь{_W}|Язык{_W} Тролля",
    103: rf"«Тропическ{_W} лагун{_W}»|Тропическ{_W} лагун{_W}",
    105: rf"[Сс]кал{_W} Слон{_W}",
}
NEVER_LINK = {50}

_COMPILED = {pid: re.compile(rf"(?<![А-Яа-яЁё\w-])(?:{pat})(?![А-Яа-яЁё\w])") for pid, pat in PLACE_ALIASES.items()}
_TOKEN_RE = re.compile(r"(<!--.*?-->|<[^>]+>)", re.S)
_SKIP_TAGS = {"a", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "small", "script", "style", "button", "code", "title"}
_LINKED_RE = re.compile(r'href="/mesta/(\d+)"')
_TAGNAME_RE = re.compile(r"<\s*(/?)\s*([a-zA-Z0-9]+)")


def linked_places(html: str) -> set[int]:
    return {int(x) for x in _LINKED_RE.findall(html or "")}


def autolink(html: str, allowed: Optional[Iterable[int]] = None, self_id: Optional[int] = None,
             max_links: int = MAX_PLACE_LINKS) -> tuple[str, list[tuple[int, str]]]:
    """Возвращает (новый html, [(id места, анкор), …]) — что было связано."""
    if not html:
        return html or "", []
    allowed_set = set(allowed) if allowed is not None else set(PLACE_ALIASES)
    done = linked_places(html)
    budget = max_links - len(done)
    if budget <= 0:
        return html, []
    targets = [pid for pid in PLACE_ALIASES
               if pid in allowed_set and pid not in done and pid != self_id and pid not in NEVER_LINK]
    if not targets:
        return html, []
    parts = _TOKEN_RE.split(html)
    stack: list[str] = []
    added: list[tuple[int, str]] = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if part.startswith("<"):
            m = _TAGNAME_RE.match(part)
            if m and not part.startswith("<!--"):
                closing, name = m.group(1) == "/", m.group(2).lower()
                if name in _SKIP_TAGS:
                    if closing:
                        if name in stack:
                            while stack and stack.pop() != name:
                                pass
                    elif not part.rstrip().endswith("/>"):
                        stack.append(name)
            continue
        if stack or budget <= 0:
            continue
        # Все кандидаты в этом куске текста, по порядку; пересечения — мимо.
        found = []
        for pid in targets:
            if pid in done:
                continue
            m = _COMPILED[pid].search(part)
            if m:
                found.append((m.start(), -(m.end() - m.start()), pid, m))
        if not found:
            continue
        found.sort()
        out, pos = [], 0
        for start, _neg, pid, m in found:
            if budget <= 0 or pid in done or start < pos:
                continue
            anchor = m.group(0)
            out.append(part[pos:start])
            out.append(f'<a href="/mesta/{pid}">{anchor}</a>')
            pos = m.end()
            done.add(pid)
            budget -= 1
            added.append((pid, anchor))
        out.append(part[pos:])
        parts[i] = "".join(out)
    return "".join(parts), added


_AUTOLINK_STRIP_RE = re.compile(r'<a href="/mesta/\d+">(.*?)</a>', re.S)


def strip_place_links(html: str) -> str:
    """Текст без ссылок на карточки — чтобы сравнивать правки независимо от
    того, связал ли автолинковщик что-то внутри."""
    return _AUTOLINK_STRIP_RE.sub(r"\1", html or "")
