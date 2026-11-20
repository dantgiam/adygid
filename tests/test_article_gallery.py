"""Галерея в тексте: старые абзацы с <img>, новые figure.shot и повторный рендер.

Разметка проверяется без базы: render_article_gallery ничего не читает и
не пишет. Повторный вызов обязан совпасть с первым — правка только на
отдаче страницы, сохранённый HTML не нормализуем разрушительно.
"""
from pathlib import Path

from site_app.galleries import render_article_gallery
from site_app.images import enhance_html_images

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = "https://hiotbrjgilwlztlfdkmg.supabase.co/storage/v1/object/public/uploads/abc.webp"
OTHER = "https://hiotbrjgilwlztlfdkmg.supabase.co/storage/v1/object/public/uploads/def.webp"


def _shot(src, alt, credit_html):
    return (
        f'<figure class="shot"><img src="{src}" alt="{alt}" loading="lazy">'
        f"<figcaption>{alt}<br><small>{credit_html}</small></figcaption></figure>"
    )


def test_old_captioned_image_becomes_centered_figure():
    html = f'<p>Текст</p><p><img src="{SAMPLE}" alt="Плато Лаго-Наки"></p>'
    out = render_article_gallery(html)
    assert out.startswith("<p>Текст</p>")
    assert 'class="article-figure"' in out
    assert 'class="article-frame"' in out
    assert 'width="1500" height="1000"' in out
    assert 'loading="lazy"' in out
    assert 'decoding="async"' in out
    assert 'alt="Плато Лаго-Наки"' in out
    assert "<span class=\"article-gallery-text\">Плато Лаго-Наки</span>" in out
    assert "data-gallery" not in out
    assert "gal-nav" not in out


def test_old_image_without_caption_stays_a_plain_insert():
    html = f'<p><img src="{SAMPLE}"></p>'
    assert render_article_gallery(html) == html


def test_old_collage_is_a_snap_carousel_with_counter_and_arrows():
    html = (
        f'<p><img src="{SAMPLE}" alt="Первый кадр">'
        f'<img src="{OTHER}" alt="Второй &quot;кадр&quot;"></p>'
    )
    out = render_article_gallery(html)
    assert out.count('class="article-gallery-item"') == 2
    assert 'class="article-gallery-track"' in out
    assert "data-gallery" in out
    assert 'data-gal-prev' in out and 'data-gal-next' in out
    assert 'gal-prev" data-gal-prev disabled' in out
    assert "1 / 2" in out and "2 / 2" in out
    assert "Первый кадр" in out
    assert "Второй &quot;кадр&quot;" in out
    assert "scroll-snap" not in out  # снап задаёт CSS, не разметка
    assert out.count('loading="lazy"') == 2
    assert out.count('width="1500" height="1000"') == 2


def test_new_shot_figures_keep_credit_and_do_not_merge_across_text():
    credit = (
        'Фото: Иванова, <a href="https://creativecommons.org/licenses/by/4.0" '
        'rel="nofollow noopener" target="_blank">CC BY 4.0</a>'
    )
    first = _shot(SAMPLE, "Туман на серпантине", credit)
    second = _shot(OTHER, "Долина Белой", credit)
    html = f"<p>До</p>{first}<p>Между кадрами живой текст.</p>{second}"
    out = render_article_gallery(html)
    assert out.count('class="article-figure"') == 2
    assert "data-gallery" not in out
    assert "Между кадрами живой текст." in out
    assert "Туман на серпантине" in out and "Долина Белой" in out
    assert out.count("article-gallery-credit") == 2
    assert 'href="https://creativecommons.org/licenses/by/4.0"' in out
    assert "Иванова" in out


def test_consecutive_shots_become_one_carousel():
    credit = 'Фото: <a href="https://commons.wikimedia.org/wiki/File:A">Commons</a>'
    html = _shot(SAMPLE, "Панорама", credit) + "\n" + _shot(OTHER, "Портрет", credit)
    out = render_article_gallery(html)
    assert out.count('class="article-gallery-item"') == 2
    assert out.count("data-gallery") == 1
    assert "1 / 2" in out and "2 / 2" in out
    assert "Панорама" in out and "Портрет" in out
    assert out.count("article-gallery-credit") == 2


def test_credit_drops_script_and_javascript_url():
    html = (
        '<figure class="shot"><img src="/uploads/a.webp" alt="Кадр">'
        '<figcaption>Кадр<br><small>Фото: <script>alert(1)</script>'
        '<a href="javascript:alert(1)">плохо</a> '
        '<a href="https://example.com/lic">лицензия</a></small></figcaption></figure>'
    )
    out = render_article_gallery(html)
    assert "<script>" not in out.lower()
    assert "javascript:" not in out.lower()
    assert "плохо" in out
    assert 'href="https://example.com/lic"' in out
    assert "alert(1)" not in out


def test_render_is_idempotent_for_old_and_new_markup():
    credit = 'Фото: <a href="https://example.com/lic">CC</a>'
    samples = [
        f'<p><img src="{SAMPLE}" alt="Один"></p>',
        f'<p><img src="{SAMPLE}" alt="Раз"><img src="{OTHER}" alt="Два"></p>',
        _shot(SAMPLE, "Туман", credit) + "<p>текст</p>" + _shot(OTHER, "Долина", credit),
        _shot(SAMPLE, "Панорама", credit) + _shot(OTHER, "Портрет", credit),
        f'<p><img src="{SAMPLE}"></p>',
    ]
    for html in samples:
        once = render_article_gallery(html)
        twice = render_article_gallery(once)
        assert twice == once, html


def test_srcset_still_applies_after_gallery_render():
    html = f'<p><img src="{SAMPLE}" alt="Плато"></p>'
    out = enhance_html_images(render_article_gallery(html))
    assert 'srcset="' in out
    assert "resize=contain" in out
    assert "Плато" in out
    assert "uploads/abc.webp" in out
    assert 'width="1500"' in out


def test_site_and_admin_share_the_frame():
    css = (ROOT / "site_app/static/site.css").read_text(encoding="utf-8")
    admin_css = (ROOT / "static/admin.css").read_text(encoding="utf-8")
    js = (ROOT / "site_app/static/site.js").read_text(encoding="utf-8")
    admin_js = (ROOT / "static/admin.js").read_text(encoding="utf-8")
    for text in (css, admin_css):
        assert "aspect-ratio: 3 / 2" in text
        assert "object-fit: cover" in text
        assert "object-position: center" in text
        assert "scroll-snap-type: x mandatory" in text
        assert "--gal-slice: 32%" in text
        assert "--gal-slice: 20%" in text
        assert "article-gallery-item:last-child" in text
        assert "#97A498" in text
    assert "data-gallery" in js and "ArrowLeft" in js
    assert "article-frame" in admin_js
    assert "coalescePhotoHtml" in admin_js
    assert "data-credit" in admin_js
