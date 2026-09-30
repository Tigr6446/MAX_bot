"""Модели и подключение к БД."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass


engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def _utcnow_naive() -> datetime:
    """Naive UTC datetime (без tzinfo) — совместим с TIMESTAMP WITHOUT TIME ZONE."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ParsedMessage(Base):
    """Сохранённое сообщение из канала с определённой категорией."""

    __tablename__ = "parsed_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(unique=True, index=True)
    message_text: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(nullable=True)

    # Дата окончания события (naive UTC). None = дата не найдена.
    event_date: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Когда пост добавлен (naive UTC) — для fallback-таймера 5 дней.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow_naive
    )


async def init_db() -> None:
    """Создаёт таблицы при старте приложения."""

        # Явно импортируем все модели, чтобы SQLAlchemy их увидел # noqa
    import app.database.model_3  # noqa
    import app.database.model_4  # noqa

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)