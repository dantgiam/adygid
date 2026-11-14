"""Адаптивные фото: трансформация Supabase, srcset, подписи не меняются."""
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://adygid:adygid@localhost:5432/adygid_test")
os.environ.setdefault("ADMIN_USER", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "adygid-test")

from site_app.images import (
    default_src,
    enhance_html_images,
    is_transformable,
    srcset,
    transform_url,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "https://hiotbrjgilwlztlfdkmg.supabase.co/storage/v1/object/public/uploads/abc.webp"


def test_transform_url_uses_contain_and_webp():
    url = transform_url(SAMPLE, 800)
    assert "/storage/v1/render/image/public/uploads/abc.webp" in url
    assert "width=800" in url
    assert "resize=contain" in url
    assert "format=webp" in url
    assert "quality=70" in url


def test_transform_is_idempotent_on_render_urls():
    first = transform_url(SAMPLE, 1280)
    again = transform_url(first, 480)
    assert again.count("render/image") == 1
    assert "width=480" in again
    assert "uploads/abc.webp" in again


def test_non_supabase_urls_pass_through():
    assert default_src("/assets/podbor/hero.webp") == "/assets/podbor/hero.webp"
    assert srcset("/assets/podbor/hero.webp") == ""
    assert default_src("") == ""
    assert not is_transformable("https://example.com/photo.jpg")


def test_srcset_lists_standard_widths():
    text = srcset(SAMPLE)
    assert " 480w" in text and " 800w" in text and " 1280w" in text
    assert text.count("resize=contain") == 3


def test_enhance_html_keeps_caption_and_adds_srcset():
    caption = "Плато Лаго-Наки зимой: наверху снег, когда в долине его ещё нет"
    html = f'<p><img src="{SAMPLE}" alt="{caption}"></p>'
    out = enhance_html_images(html)
    assert caption in out
    assert 'srcset="' in out
    assert "format=webp" in out
    assert 'loading="lazy"' in out
    # Не подменяем кадр на другой объект в хранилище.
    assert "uploads/abc.webp" in out


def test_enhance_skips_local_assets():
    html = '<img src="/assets/magnet-max.png" alt="MAX">'
    assert enhance_html_images(html) == html


def test_templates_and_js_wire_srcset():
    cards = (ROOT / "site_app/templates/_cards.html").read_text(encoding="utf-8")
    assert "img_srcset" in cards
    assert "macro rimg" in cards
    js = "\n".join([
        (ROOT / "site_app/static/site.js").read_text(encoding="utf-8"),
        (ROOT / "site_app/static/podbor.js").read_text(encoding="utf-8"),
    ])
    assert "window.adygidImg" in js
    assert "resize=contain" in js
    assert "photoSrc(" in js
    assert "format=webp" in js
    home = (ROOT / "site_app/templates/home.html").read_text(encoding="utf-8")
    place = (ROOT / "site_app/templates/place_detail.html").read_text(encoding="utf-8")
    assert "cards.rimg" in home and "fetchpriority='high'" in home
    assert "cards.rimg" in place and "img_sizes.hero" in place
