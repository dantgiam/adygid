"""Скрытый черновик-превью блока «Коротко для поездки». База не нужна."""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from site_app import seo

ROOT = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
router = APIRouter()

# Имена только для превью; в проде блок берёт название из карточки.
PLACE_NAMES = {
    24: "Хаджохская теснина",
    40: "Водопады Руфабго",
    62: "Музей природы Кавказского заповедника",
    63: "Вольерный комплекс в Гузерипле",
    52: "Гранитный каньон",
    55: "Плато Лаго-Наки",
    48: "Савранская канатная дорога",
    67: "«АкваТермо»: термальные бассейны в Тульском",
    68: "«Кедровый бор»: термальный бассейн в Цветочном",
    72: "Термы Псыгупс",
    25: "Большая Азишская пещера",
    42: "Казачий камень",
    45: "Музей «Беловодье» в Хаджохе",
    56: "Каменное море",
    57: "Азишский перевал: панорама у дороги",
    43: "Экстрим-парк «Мишоко»",
    49: "Старый мост в Даховской",
    30: "Михайло-Афонская пустынь",
    64: "Яворова поляна",
}

# Карточки, которые в этой ветке получили новые официальные факты.
UPDATED = {24, 55, 62, 63, 48, 67, 56, 57, 43, 49, 30, 64}

VARIANTS = {"kompakt": "A", "istochniki": "B", "kartochki": "C"}


def _rows(pid: int, cfg: dict) -> list[dict]:
    rows = []
    for key, label in seo.PRACTICAL_LABELS:
        if key == "combine":
            ids = [i for i in cfg.get("combine", []) if i != pid]
            if not ids and not cfg.get("route"):
                continue
            names = [PLACE_NAMES.get(i, f"место {i}") for i in ids]
            if cfg.get("route"):
                names.append(f"маршрут {cfg['route']}")
            rows.append({"key": key, "label": label, "text": ", ".join(names), "source": None})
            continue
        value = cfg.get(key)
        if not value:
            continue
        if isinstance(value, dict):
            rows.append({"key": key, "label": label, "text": value["text"], "source": value.get("source")})
        else:
            rows.append({"key": key, "label": label, "text": value, "source": None})
    return rows


def _places():
    out = []
    for pid, cfg in seo.PLACE_PRACTICAL.items():
        out.append({
            "id": pid,
            "name": PLACE_NAMES.get(pid, f"Место {pid}"),
            "updated": pid in UPDATED,
            "rows": _rows(pid, cfg),
        })
    return out


@router.get("/chernovik/korotko-dlya-poezdki/", include_in_schema=False)
def slash():
    return RedirectResponse("/chernovik/korotko-dlya-poezdki", status_code=307)


@router.get("/chernovik/korotko-dlya-poezdki", include_in_schema=False)
def preview(request: Request, v: str = "kompakt", ids: str = ""):
    variant = v if v in VARIANTS else "kompakt"
    places = _places()
    if ids:
        wanted = {int(x) for x in ids.split(",") if x.strip().isdigit()}
        places = [p for p in places if p["id"] in wanted]
    response = templates.TemplateResponse(
        "trip_brief_preview.html",
        {
            "request": request,
            "variant": variant,
            "places": places,
            "rev": int(datetime.now().timestamp()),
            "canonical_url": str(request.base_url).rstrip("/") + "/chernovik/korotko-dlya-poezdki",
        },
    )
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
