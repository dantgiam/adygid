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
    # Дата последней правки — показывается на сайте как «Проверено …»:
    # для описаний с ценами и состоянием троп это сигнал свежести.
    updated_at       = Column(DateTime, server_default=func.now(), onupdate=func.now())

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

    category = relationship("Category")
    trail    = relationship("Trail", back_populates="checkpoints")
    photos   = relationship("Photo", back_populates="checkpoint", cascade="all, delete-orphan")


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
