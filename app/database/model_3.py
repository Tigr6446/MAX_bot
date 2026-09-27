"""Модель пользователя для БД."""

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.model_1 import Base
from app.database.model_1 import async_session as AsyncSessionLocal


class User(Base):
    """Пользователь бота — с настройками профиля."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    region: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    city: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    categories: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )