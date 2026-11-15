"""Три зимние статьи: текст, ссылки, уникальные заголовки и безопасный SQL."""
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_PY = ROOT / "content" / "winter-intent-2026-11" / "articles.py"
SQL_FORWARD = ROOT / "migrations" / "20261115_winter_intent_articles.sql"
SQL_ROLLBACK = ROOT / "migrations" / "20261115_winter_intent_articles_rollback.sql"

FORBIDDEN = re.compile(
    r"терм|акватермо|псыгупс|кедров|/mesta/67\b|/mesta/68\b|/mesta/72\b|"
    r"/stati/termal|дешевле|₽|/mesta/50\b|/marshruty/11\b",
    re.I,
)
HREF_RE = re.compile(r'href="([^"]+)"')
HEAD_RE = re.compile(r"<h[23]>[^<]+</h[23]>\s*<p><strong>")


def _load():
    spec = importlib.util.spec_from_file_location("winter_articles", ARTICLES_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pack():
    return _load()


def _visible(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def test_three_pages_have_unique_titles_and_answers(pack):
    titles = [a["title"] for a in pack.ARTICLES]
    excerpts = [a["excerpt"] for a in pack.ARTICLES]
    assert len(titles) == len(set(titles)) == 3
    assert len(excerpts) == len(set(excerpts)) == 3
    assert {a["id"] for a in pack.ARTICLES} == {33, 14, 15}
    assert {a["slug"] for a in pack.ARTICLES} == {
        "adygeya-v-dekabre",
        "lago-naki-zimoy-na-mashine",
        "pervyy-sneg-na-lago-naki-ehat-ili-net",
    }
    for article in pack.ARTICLES:
        assert len(article["title"]) <= 255
        assert len(article["excerpt"]) <= 500
        assert article["title"] != article["before"]["title"]
        assert article["excerpt"] != article["before"]["excerpt"]
        assert "<h1" not in article["body"].lower()
        assert article["body"].startswith("<p><strong>")
        assert len(re.findall(r"<h2>", article["body"])) >= 3
        assert not FORBIDDEN.search(article["title"] + article["excerpt"] + article["body"])
        for item in article["faq"]:
            assert item["question"] and item["answer"]
            assert not FORBIDDEN.search(item["question"] + item["answer"])
        headings = re.findall(r"<h[23]>([^<]+)</h[23]>", article["body"])
        assert len(headings) == len(set(headings))
        assert HEAD_RE.findall(article["body"])
        # каждый вопрос-заголовок сразу получает короткий ответ
        assert len(HEAD_RE.findall(article["body"])) == len(headings)


def test_photos_and_credits_are_the_live_ones(pack):
    for article in pack.ARTICLES:
        before = article["before"]["body"]
        for figure in re.findall(r'<figure class="shot">.*?</figure>', before, re.S):
            assert figure in article["body"]
        credit = re.search(r'<p class="photo-credit">.*?</p>', before, re.S).group(0)
        assert credit in article["body"]
        assert article["before"]["cover_url"]  # обложку миграция не переписывает
        assert article["before"]["slug"] == article["slug"]


def test_each_page_keeps_one_job(pack):
    by_slug = {a["slug"]: a for a in pack.ARTICLES}
    december = by_slug["adygeya-v-dekabre"]["body"]
    road = by_slug["lago-naki-zimoy-na-mashine"]["body"]
    snow = by_slug["pervyy-sneg-na-lago-naki-ehat-ili-net"]["body"]
    assert "Кому поездка в декабре подходит?" in december
    assert "1780" not in december and "дешевле" not in december
    assert "Пункт 5.2" in road and "не гарантирует" in road
    assert "31 декабря 2025" in road and "сегодня закрыто" in road
    assert "не гарантирует" in road
    assert "Подтверждённого рейса до КПП" in road
    assert "не обновляет текст автоматически" in snow
    assert "9 ноября 2026" in snow and "30 см" in snow and "таймауту" in snow
    assert "снег есть сегодня" not in snow
    # перекрёстные ссылки есть, но страницы не слиты в один текст
    assert "/stati/lago-naki-zimoy-na-mashine" in december
    assert "/stati/pervyy-sneg-na-lago-naki-ehat-ili-net" in december
    assert "/stati/pervyy-sneg-na-lago-naki-ehat-ili-net" in road
    assert "/stati/adygeya-v-dekabre" in snow
    assert "Пункт 5.2" not in snow
    assert by_slug["adygeya-v-dekabre"]["featured_checkpoint_ids"] == [24, 40, 62, 55]
    assert 67 not in by_slug["adygeya-v-dekabre"]["featured_checkpoint_ids"]


def test_december_build_source_matches_migration_text(pack):
    spec = importlib.util.spec_from_file_location(
        "seo_build", ROOT / "content" / "seo-2026-11" / "build.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    built = next(a for a in json.loads(
        (ROOT / "content" / "seo-2026-11" / "content.json").read_text(encoding="utf-8")
    )["articles"] if a["slug"] == "adygeya-v-dekabre")
    live = next(a for a in pack.ARTICLES if a["slug"] == "adygeya-v-dekabre")
    assert _visible(built["body"]) == _visible(live["body"])
    assert built["title"] == live["title"]
    assert built["excerpt"] == live["excerpt"]
    assert built["featured_checkpoint_ids"] == live["featured_checkpoint_ids"]
    assert built["faq"] == live["faq"]


def test_sql_is_guarded_and_does_not_touch_other_tables():
    forward = SQL_FORWARD.read_text(encoding="utf-8")
    rollback = SQL_ROLLBACK.read_text(encoding="utf-8")
    for text in (forward, rollback):
        assert "WHERE id NOT IN (14, 15, 33)" in text
        assert "trail-11" in text and "place-50" in text
        assert "не совпал ни со снимком" in text
        assert "UPDATE trails" not in text
        assert "UPDATE checkpoints" not in text
        assert "UPDATE partners" not in text
        assert "metrica" not in text.lower()
        for slug in (
            "adygeya-v-dekabre",
            "lago-naki-zimoy-na-mashine",
            "pervyy-sneg-na-lago-naki-ehat-ili-net",
        ):
            assert slug in text
    assert "Стоит ли ехать в Адыгею в декабре" in forward
    assert "Адыгея в декабре: погода, снег и интересные места" in rollback
    assert "Как доехать до Лаго-Наки зимой" in forward
    assert "Есть ли снег на Лаго-Наки" in forward


def _seed(conn, pack):
    conn.execute("DROP TABLE IF EXISTS articles, trails, checkpoints")
    conn.execute(
        """
        CREATE TABLE articles (
          id integer primary key,
          slug varchar(200) not null unique,
          title varchar(255) not null,
          excerpt varchar(500),
          cover_url varchar(500),
          body text not null default '',
          faq jsonb not null default '[]'::jsonb,
          district varchar(30),
          featured_checkpoint_ids integer[] not null default '{}',
          featured_trail_ids integer[] not null default '{}',
          is_published boolean not null default true,
          updated_at timestamp default now()
        )
        """
    )
    conn.execute("CREATE TABLE trails (id integer primary key, name text, description text)")
    conn.execute("CREATE TABLE checkpoints (id integer primary key, name text, description text)")
    conn.execute(
        "INSERT INTO trails (id, name, description) VALUES (11, %s, %s)",
        ("Чёртов палец – пеший маршрут", "frozen-route-11"),
    )
    conn.execute(
        "INSERT INTO checkpoints (id, name, description) VALUES (50, %s, %s)",
        ("Место 50", "frozen-place-50"),
    )
    conn.execute(
        """
        INSERT INTO articles (id, slug, title, excerpt, cover_url, body, faq, is_published, featured_checkpoint_ids, featured_trail_ids)
        VALUES (99, 'decoy', 'Чужая', 'не трогать', NULL, 'decoy-body', '[]'::jsonb, TRUE, '{}', '{}')
        """
    )
    for article in pack.ARTICLES:
        before = article["before"]
        conn.execute(
            """
            INSERT INTO articles (
              id, slug, title, excerpt, cover_url, body, faq, district, is_published,
              featured_checkpoint_ids, featured_trail_ids
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, TRUE, %s, %s)
            """,
            (
                before["id"], before["slug"], before["title"], before["excerpt"], before["cover_url"],
                before["body"], json.dumps(before["faq"] or [], ensure_ascii=False),
                before["district"], list(before["featured_checkpoint_ids"] or []),
                list(before["featured_trail_ids"] or []),
            ),
        )


def _psql(path: Path) -> None:
    subprocess.run(
        ["psql", "postgresql://adygid:adygid@localhost:5432/adygid_winter_sql",
         "-v", "ON_ERROR_STOP=1", "-f", str(path)],
        check=True, capture_output=True, text=True,
    )


def test_sql_roundtrip_refuses_drift_and_spares_route11_place50(pack):
    psycopg = pytest.importorskip("psycopg")
    admin = psycopg.connect("postgresql://adygid:adygid@localhost:5432/postgres", autocommit=True)
    admin.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'adygid_winter_sql' AND pid <> pg_backend_pid()"
    )
    admin.execute("DROP DATABASE IF EXISTS adygid_winter_sql")
    admin.execute("CREATE DATABASE adygid_winter_sql")
    admin.close()
    with psycopg.connect("postgresql://adygid:adygid@localhost:5432/adygid_winter_sql", autocommit=True) as conn:
        _seed(conn, pack)
        _psql(SQL_FORWARD)
        rows = {row[0]: row for row in conn.execute(
            "SELECT id, title, excerpt, cover_url, featured_checkpoint_ids, featured_trail_ids, is_published, slug FROM articles ORDER BY id"
        )}
        assert rows[33][1] == "Стоит ли ехать в Адыгею в декабре"
        assert rows[14][1] == "Как доехать до Лаго-Наки зимой"
        assert rows[15][1] == "Есть ли снег на Лаго-Наки"
        assert rows[99][1] == "Чужая"
        assert conn.execute("SELECT body FROM articles WHERE id = 99").fetchone()[0] == "decoy-body"
        assert conn.execute("SELECT name, description FROM trails WHERE id = 11").fetchone() == (
            "Чёртов палец – пеший маршрут", "frozen-route-11",
        )
        assert conn.execute("SELECT name, description FROM checkpoints WHERE id = 50").fetchone() == (
            "Место 50", "frozen-place-50",
        )
        for article in pack.ARTICLES:
            row = rows[article["id"]]
            assert row[2] == article["excerpt"]
            assert row[3] == article["before"]["cover_url"]
            assert list(row[4]) == article["featured_checkpoint_ids"]
            assert list(row[5]) == list(article["before"]["featured_trail_ids"] or [])
            assert row[6] is True and row[7] == article["slug"]
        _psql(SQL_FORWARD)  # повтор ничего не ломает
        assert conn.execute("SELECT title FROM articles WHERE id = 33").fetchone()[0].startswith("Стоит ли")
        _psql(SQL_ROLLBACK)
        assert conn.execute("SELECT title FROM articles WHERE id = 33").fetchone()[0] == pack.ARTICLES[0]["before"]["title"]
        assert conn.execute("SELECT description FROM trails WHERE id = 11").fetchone()[0] == "frozen-route-11"
        _psql(SQL_ROLLBACK)
        conn.execute("UPDATE articles SET body = 'чужая правка' WHERE id = 33")
        with pytest.raises(subprocess.CalledProcessError):
            _psql(SQL_FORWARD)
        assert conn.execute("SELECT body FROM articles WHERE id = 33").fetchone()[0] == "чужая правка"
        assert conn.execute("SELECT title FROM articles WHERE id = 14").fetchone()[0] == pack.ARTICLES[1]["before"]["title"]
        assert conn.execute("SELECT body FROM articles WHERE id = 99").fetchone()[0] == "decoy-body"
        assert conn.execute("SELECT description FROM checkpoints WHERE id = 50").fetchone()[0] == "frozen-place-50"


def test_internal_links_resolve_and_titles_do_not_collide(pack):
    import urllib.request

    paths = set()
    external = set()
    for article in pack.ARTICLES:
        for href in HREF_RE.findall(article["body"]):
            if href.startswith("/"):
                paths.add(href.split("#")[0])
            else:
                external.add(href)
    assert paths
    opener = urllib.request.build_opener()
    for path in sorted(paths):
        url = "https://www.adygid.ru" + path
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "AdyGidContentReview/1.0"})
        with opener.open(req, timeout=30) as response:
            assert response.status == 200, url
    soft = ("01.mchs.gov.ru", "xn--90adear.xn--p1ai")
    for url in sorted(external):
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "AdyGidContentReview/1.0"})
        try:
            with opener.open(req, timeout=25) as response:
                assert response.status == 200, url
        except Exception as exc:  # noqa: BLE001
            if any(host in url for host in soft):
                continue
            raise AssertionError(f"{url} не открылась: {exc}") from exc
    req = urllib.request.Request(
        "https://www.adygid.ru/api/articles",
        headers={"User-Agent": "AdyGidContentReview/1.0"},
    )
    with opener.open(req, timeout=30) as response:
        live = json.loads(response.read().decode())
    others = {(a["title"], a["excerpt"]) for a in live if a["slug"] not in {x["slug"] for x in pack.ARTICLES}}
    for article in pack.ARTICLES:
        assert (article["title"], article["excerpt"]) not in others
        assert article["title"] not in {title for title, _ in others}
