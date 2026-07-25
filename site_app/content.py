"""Статичные справочники нового публичного сайта — округа и подписи для фильтров.

Список типов мест/маршрутов не здесь: он живёт в таблице categories
(is_public=True) и наполняется через админку.
"""

DISTRICTS = {
    "maikop": "Округ Майкопа",
    "khadzhokh": "Округ Хаджоха",
    "dakhovskaya": "Округ Даховской",
    "lagonaki": "Плато Лагонаки",
    "guzeripl": "Округ Гузерипля",
}

DIFFICULTY_LABELS = {
    "easy": "Лёгкая",
    "medium": "Средняя",
    "hard": "Сложная",
}

SEASON_LABELS = {
    "year_round": "Круглый год",
    "summer_only": "Только летом",
}

ACCESS_LABELS = {
    "paved": "На машине по асфальту",
    "high_clearance": "Нужен клиренс",
    "foot_only": "Только пешком",
}

# Вес для взвешенного случайного выбора — топовые места должны выпадать реже
POPULARITY_WEIGHT = {
    "top": 1,
    "popular": 3,
    "normal": 6,
}

POPULARITY_LABELS = {
    "top": "ТОП",
}
