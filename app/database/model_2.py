"""Модель для событий, спарсенных с сайтов (dobro.ru и т.п.)."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.model_1 import Base


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WebEvent(Base):
    """Событие, спарсенное с внешнего сайта."""

    __tablename__ = "web_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    message_text: Mapped[str] = mapped_column(Text)

    # Регион и город события
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Категория (например, volunteering)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Дата окончания события (naive UTC). None = дата не найдена.
    event_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Когда добавлено — для fallback-таймера
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)