from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from app.database import Base


class Category(Base):
    """
    Категория маршрута и/или точки. Создаётся и удаляется гидом в админке.
    type: 'trail' | 'checkpoint' | 'both' — где категория доступна для выбора.
    is_public: показывается ли как фильтр на публичном сайте (False — служебные
    метки вроде "Начало маршрута", нужны только для редактора в админке).
    """
    __tablename__ = "categories"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100), nullable=False)
    type       = Column(String(20), nullable=False, default="both")   # trail / checkpoint / both
    icon       = Column(String(10), nullable=True)                    # эмодзи-иконка
    is_public  = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())


class Trail(Base):
    """
    Маршрут — это «папка». Сам по себе не хранит геометрию.
    Геометрия разбита на сегменты (TrailSegment), каждый со своей сложностью.
    """
    __tablename__ = "trails"

    id               = Column(Integer, primary_key=True, index=True)
    name             = Column(String(255), nullable=False)
    description      = Column(Text, nullable=True)
    category_id      = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    created_at       = Column(DateTime, server_default=func.now())
    # Дата последней правки — техническая, не показывается гостю.
    updated_at       = Column(DateTime, server_default=func.now(), onupdate=func.now())
    # А вот дата на сайте («Актуально на …») выставляется гидом вручную:
    # автообновление на каждую правку текста вводило в заблуждение — дата
    # «плыла» даже когда поправили опечатку, а не перепроверили маршрут.
    checked_at       = Column(DateTime, nullable=True)
    # Скрыть из публичных списков и с прямых ссылок, не удаляя черновик.
    is_published     = Column(Boolean, nullable=False, default=True)

    # ── Критерии фильтрации (см. adygid_filters_spec.md) ──
    # difficulty — интегральная сложность всего маршрута, выставляется автором
    # вручную; отдельно от TrailSegment.difficulty (по-сегментно, для покраски тропы).
    difficulty      = Column(String(20), nullable=False, default="medium")       # easy / medium / hard
    surface_types   = Column(ARRAY(String(30)), nullable=False, default=list)    # asphalt / dirt / trail / scramble
    seasonality     = Column(String(20), nullable=False, default="year_round")   # year_round / summer_only
    weather_warning = Column(Boolean, nullable=False, default=False)             # предупреждение, не фильтр
    access_type     = Column(String(30), nullable=False, default="foot_only")    # paved / high_clearance / foot_only
    is_paid         = Column(Boolean, nullable=False, default=False)
    price_note      = Column(String(255), nullable=True)
    equipment_tags  = Column(ARRAY(String(50)), nullable=False, default=list)
    kid_friendly    = Column(Boolean, nullable=False, default=False)

    # ── Публичный сайт: округ (география) и ручная популярность ──
    district    = Column(String(30), nullable=True)                          # maikop / khadzhokh / dakhovskaya / lagonaki / guzeripl
    popularity  = Column(String(20), nullable=False, default="normal")       # normal / popular / top

    # Ссылка «Открыть в Яндекс Навигаторе». Пусто — строится автоматически из
    # координат точек маршрута (см. site_app/router.py, _yandex_route_url);
    # заполнено вручную — используется как есть (например, готовый маршрут
    # с точками привязки, который автогенерация не соберёт один в один).
    yandex_url  = Column(String(500), nullable=True)

    category    = relationship("Category")
    segments    = relationship("TrailSegment",  back_populates="trail", cascade="all, delete-orphan", order_by="TrailSegment.order_index")
    checkpoints = relationship("Checkpoint",    back_populates="trail", cascade="all, delete-orphan", order_by="Checkpoint.order_index")
    photos      = relationship("Photo",         back_populates="trail", cascade="all, delete-orphan")


class TrailSegment(Base):
    """
    Один кусок тропы — LineString с конкретной сложностью.
    Один маршрут может иметь любое количество сегментов.
    Порядок задаётся order_index (0, 1, 2, …).
    """
    __tablename__ = "trail_segments"

    id          = Column(Integer, primary_key=True, index=True)
    trail_id    = Column(Integer, ForeignKey("trails.id"), nullable=False)
    difficulty  = Column(String(20), nullable=False, default="easy")   # easy / medium / hard
    order_index = Column(Integer, nullable=False, default=0)
    geom        = Column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=False)

    trail = relationship("Trail", back_populates="segments")


class Checkpoint(Base):
    """
    Точка внутри маршрута (или самостоятельная точка без trail_id).
    Имеет порядковый номер, описание и фотографии.
    """
    __tablename__ = "checkpoints"

    id               = Column(Integer, primary_key=True, index=True)
    trail_id         = Column(Integer, ForeignKey("trails.id"), nullable=True)
    name             = Column(String(255), nullable=False)
    category_id      = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    description      = Column(Text, nullable=True)
    order_index      = Column(Integer, nullable=False, default=0)
    geom             = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    created_at       = Column(DateTime, server_default=func.now())
    updated_at       = Column(DateTime, server_default=func.now(), onupdate=func.now())
    checked_at       = Column(DateTime, nullable=True)
    is_published     = Column(Boolean, nullable=False, default=True)
    duration_minutes = Column(Integer, nullable=True)

    # ── Критерии фильтрации (см. adygid_filters_spec.md) — тот же набор, что у Trail,
    # чтобы отдельно стоящие точки тоже участвовали в фильтрах наравне с маршрутами.
    difficulty      = Column(String(20), nullable=False, default="medium")
    surface_types   = Column(ARRAY(String(30)), nullable=False, default=list)
    seasonality     = Column(String(20), nullable=False, default="year_round")
    weather_warning = Column(Boolean, nullable=False, default=False)
    access_type     = Column(String(30), nullable=False, default="foot_only")
    is_paid         = Column(Boolean, nullable=False, default=False)
    price_note      = Column(String(255), nullable=True)
    equipment_tags  = Column(ARRAY(String(50)), nullable=False, default=list)
    kid_friendly    = Column(Boolean, nullable=False, default=False)

    # ── Публичный сайт: округ (география) и ручная популярность ──
    district    = Column(String(30), nullable=True)                          # maikop / khadzhokh / dakhovskaya / lagonaki / guzeripl
    popularity  = Column(String(20), nullable=False, default="normal")       # normal / popular / top

    # Показывать ли точку в разделе «Места» отдельной карточкой. Промежуточные
    # точки маршрута (развилки, привалы) нужны только внутри маршрута — для них
    # флаг снят, и своей страницы у них нет.
    show_as_place = Column(Boolean, nullable=False, default=True)

    # Ссылка «Открыть в Яндекс Навигаторе» — см. Trail.yandex_url.
    yandex_url = Column(String(500), nullable=True)

    category = relationship("Category")
    trail    = relationship("Trail", back_populates="checkpoints")
    photos   = relationship("Photo", back_populates="checkpoint", cascade="all, delete-orphan")


class Magnet(Base):
    """
    Лид-магнит — акцентный блок внутри текста статьи: «у меня есть готовый
    чек-лист, он в закреплённых» + кнопка в клуб.

    Блок переиспользуемый: в теле статьи хранится только ссылка на id
    (<div class="magnet-embed" data-magnet-id="N"></div>), а текст и ссылки
    подставляются на рендере из этой таблицы. Поправил магнит — обновилось
    везде, где он вставлен.

    Ссылки на мессенджеры обе необязательные: если задана одна — читателя
    ведём сразу в неё, если обе — сначала показываем выбор. Если не задано
    ни одной, блок на сайте не выводится вовсе, чтобы не публиковать
    кнопку в никуда.
    """
    __tablename__ = "magnets"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(255), nullable=False)   # служебное имя для списка в админке
    title         = Column(String(255), nullable=False)   # заголовок-приманка
    text          = Column(Text, nullable=True)           # пояснение под заголовком
    button_text   = Column(String(120), nullable=False, default="Забрать в клубе")
    note          = Column(String(255), nullable=True)    # мелкая подпись под кнопкой
    telegram_url  = Column(String(500), nullable=True)
    max_url       = Column(String(500), nullable=True)
    is_published  = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime, server_default=func.now())


class FaqSet(Base):
    """
    Именованный набор вопросов-ответов («Общие», «Без машины», «С детьми»).

    Вставляется в статью так же, как лид-магнит — по id
    (<div class="faq-embed" data-faq-id="N"></div>), поэтому правка набора
    подхватывается везде, где он вставлен. Ответы хранятся как HTML
    (абзацы, списки, ссылки) — их набирают в визуальном редакторе.

    items: [{"question": "...", "answer": "<p>...</p>"}] — порядок в списке
    и есть порядок на странице.
    """
    __tablename__ = "faq_sets"

    id           = Column(Integer, primary_key=True, index=True)
    slug         = Column(String(200), nullable=False, unique=True, index=True)
    name         = Column(String(255), nullable=False)   # для списка в админке
    title        = Column(String(255), nullable=True)    # заголовок над блоком
    items        = Column(JSONB, nullable=False, default=list)
    # Показывать ли набор на общей странице /voprosy
    on_faq_page  = Column(Boolean, nullable=False, default=False)
    order_index  = Column(Integer, nullable=False, default=0)
    is_published = Column(Boolean, nullable=False, default=True)
    created_at   = Column(DateTime, server_default=func.now())


class Scenario(Base):
    """
    Дверь развилки на главной («Еду с детьми», «Без машины» и т.п.) — вход
    на сайт по ситуации человека, а не по типу контента.

    Места и маршруты на странице сценария не перечисляются вручную: подходящие
    вытягиваются из базы по filter_*-полям (site_app/router.py, _scenario_conditions).
    Пустой список/None в filter_* значит «без ограничения по этому признаку» —
    так работает и создание нового сценария (по умолчанию берёт всё), и сброс
    фильтра обратно в «неважно» при редактировании.
    """
    __tablename__ = "scenarios"

    id                    = Column(Integer, primary_key=True, index=True)
    slug                  = Column(String(200), nullable=False, unique=True, index=True)
    icon                  = Column(String(10), nullable=True)      # эмодзи на плитке
    door                  = Column(String(255), nullable=False)    # подпись плитки в развилке
    hint                  = Column(String(255), nullable=True)     # подзаголовок плитки
    title                 = Column(String(255), nullable=False)    # заголовок страницы сценария
    lead                  = Column(Text, nullable=True)     # HTML из Quill-редактора в админке
    cover_url             = Column(String(500), nullable=True)     # шапка страницы сценария
    cover_thumb_url       = Column(String(500), nullable=True)
    cover_focus           = Column(String(20), nullable=True)
    # Отдельное вертикальное фото для плитки развилки — шапка страницы горизонтальная,
    # для карточки нужен свой кадр, а не автоматический кроп той же картинки.
    tile_cover_url        = Column(String(500), nullable=True)
    tile_cover_thumb_url  = Column(String(500), nullable=True)
    tile_cover_focus      = Column(String(20), nullable=True)
    seo_description       = Column(String(500), nullable=True)
    featured_article_ids  = Column(ARRAY(Integer), nullable=False, default=list)

    # ── Правило отбора — см. docstring выше ──
    filter_kid_friendly = Column(Boolean, nullable=True)
    filter_popularity   = Column(ARRAY(String(20)), nullable=False, default=list)
    filter_difficulty   = Column(ARRAY(String(20)), nullable=False, default=list)
    filter_seasonality  = Column(String(20), nullable=True)
    filter_access       = Column(ARRAY(String(30)), nullable=False, default=list)

    order_index  = Column(Integer, nullable=False, default=0)
    is_published = Column(Boolean, nullable=False, default=True)
    created_at   = Column(DateTime, server_default=func.now())


class Article(Base):
    """
    Статья для статей-хаба на публичном сайте (что взять с собой, куда поехать и т.д.).
    featured_checkpoint_ids / featured_trail_ids — места и маршруты, которые
    показываются карточками прямо в статье (ручной выбор гида в админке).
    """
    __tablename__ = "articles"

    id                     = Column(Integer, primary_key=True, index=True)
    slug                   = Column(String(200), nullable=False, unique=True, index=True)
    title                  = Column(String(255), nullable=False)
    excerpt                = Column(String(500), nullable=True)
    cover_url              = Column(String(500), nullable=True)
    # Уменьшенная копия обложки — её показывают карточки статей; оригинал
    # весит мегабайты и нужен только на самой странице.
    cover_thumb_url        = Column(String(500), nullable=True)
    cover_focus            = Column(String(20), nullable=True)
    body                   = Column(Text, nullable=False, default="")
    # Список {"question": "...", "answer": "..."} — рендерится и текстом в
    # конце статьи, и как JSON-LD FAQPage для расширенного сниппета в поиске.
    faq                    = Column(JSONB, nullable=False, default=list)
    district               = Column(String(30), nullable=True)
    featured_checkpoint_ids = Column(ARRAY(Integer), nullable=False, default=list)
    featured_trail_ids      = Column(ARRAY(Integer), nullable=False, default=list)
    is_published           = Column(Boolean, nullable=False, default=True)
    created_at             = Column(DateTime, server_default=func.now())


class Photo(Base):
    """Фото привязывается либо к чекпоинту, либо к маршруту (ровно к одному из них)."""
    __tablename__ = "photos"

    id            = Column(Integer, primary_key=True, index=True)
    checkpoint_id = Column(Integer, ForeignKey("checkpoints.id"), nullable=True)
    trail_id      = Column(Integer, ForeignKey("trails.id"), nullable=True)
    url           = Column(String(500), nullable=False)
    thumb_url     = Column(String(500), nullable=True)
    caption       = Column(String(255), nullable=True)
    focus         = Column(String(20), nullable=True)

    checkpoint = relationship("Checkpoint", back_populates="photos")
    trail      = relationship("Trail", back_populates="photos")


class Like(Base):
    """Анонимный лайк «Пригодилось» на месте или маршруте публичного сайта.
    voter_id — случайный ID из cookie браузера (не аккаунт), уникальный индекс
    не даёт одному и тому же браузеру засчитать лайк дважды."""
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("subject_type", "subject_id", "voter_id", name="uq_like_voter"),)

    id           = Column(Integer, primary_key=True, index=True)
    subject_type = Column(String(20), nullable=False)   # checkpoint / trail
    subject_id   = Column(Integer, nullable=False)
    voter_id     = Column(String(64), nullable=False)
    created_at   = Column(DateTime, server_default=func.now())


class SitePage(Base):
    """Тексты статических страниц сайта (шапка главной, страница клуба) —
    раньше были зашиты прямо в HTML-шаблон, теперь правятся в админке без
    деплоя. Строки на 'home' и 'club' засеваются один раз при первом старте
    (см. app/main.py) и дальше всегда существуют, поэтому публичные роуты
    читают их без доп. проверки на None."""
    __tablename__ = "site_pages"

    id          = Column(Integer, primary_key=True, index=True)
    slug        = Column(String(50), nullable=False, unique=True, index=True)   # 'home' | 'club'
    eyebrow     = Column(String(100), nullable=True)
    title       = Column(String(255), nullable=True)
    lead        = Column(Text, nullable=True)
    # Главная: подпись на фото автора. Клуб: второй абзац под lead.
    lead_extra  = Column(Text, nullable=True)
    button_text = Column(String(120), nullable=True)

    # Фото рядом с текстом шапки: на главной — портрет автора (он же
    # доказательство «прошёл сам»), на клубе — тот же кадр в квадрате.
    # Кадрирование хранится строкой «50% 30%» / «50% 30% 1.4», как у обложек.
    cover_url       = Column(String(500), nullable=True)
    cover_thumb_url = Column(String(500), nullable=True)
    cover_focus     = Column(String(20), nullable=True)

    # Список карточек страницы: на клубе это «О чём спрашивают» —
    # [{"topic": "Погода", "question": "…"}]. Порядок в списке = порядок на странице.
    items = Column(JSONB, nullable=False, server_default="[]")

    # Куда ведут кнопки клуба. Пусто — берётся константа CLUB_URL
    # (site_app/content.py), чтобы страница работала до первой правки в админке.
    telegram_url = Column(String(500), nullable=True)
    max_url      = Column(String(500), nullable=True)

    updated_at  = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DifficultyLevel(Base):
    """Шкала сложности — четыре уровня с подписью, пояснением и цветом.
    Раньше жила константой DIFFICULTY_INFO в site_app/content.py и правилась
    только деплоем. Уровни засеваются один раз при первом старте, новые через
    админку не заводятся: их ровно четыре, и код каждого зашит в данные мест
    и маршрутов."""
    __tablename__ = "difficulty_levels"

    id          = Column(Integer, primary_key=True, index=True)
    code        = Column(String(20), nullable=False, unique=True, index=True)  # easy|medium|hard|extreme
    title       = Column(String(60), nullable=False)
    text        = Column(Text, nullable=False)
    color       = Column(String(20), nullable=False)
    dots        = Column(Integer, nullable=False, default=1)
    order_index = Column(Integer, nullable=False, default=0)


class District(Base):
    """Округ — теперь полноценная сущность, а не константа в content.py.
    Правится в админке: название, вступление, факты списком, обложка.
    slug остаётся ключом — он записан в district у мест, маршрутов и статей,
    поэтому его не меняют после создания."""
    __tablename__ = "districts"

    id              = Column(Integer, primary_key=True, index=True)
    slug            = Column(String(50), nullable=False, unique=True, index=True)
    name            = Column(String(120), nullable=False)
    lead            = Column(Text, nullable=True)
    facts           = Column(JSONB, nullable=False, server_default="[]")
    cover_url       = Column(String(500), nullable=True)
    cover_thumb_url = Column(String(500), nullable=True)
    cover_focus     = Column(String(20), nullable=True)
    order_index     = Column(Integer, nullable=False, default=0)
    is_published    = Column(Boolean, nullable=False, default=True)
