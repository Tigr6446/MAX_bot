from datetime import datetime

from sqlalchemy import DateTime, String, func
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


class ParsedMessage(Base):
    """Сохранённое сообщение из канала с определённой категорией."""

    __tablename__ = "parsed_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True
    )
    message_text: Mapped[str] = mapped_column(String(6000)) #убрать ограничение!!!
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    # Поля под код НИКИТЫ (пока не заполняются парсером)
    event_date: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )


async def init_db() -> None:
    #Создаёт таблицы при старте приложения.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)