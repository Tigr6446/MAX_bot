
"""Модель для архивации обработанных сообщений."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.model_1 import Base


class ProcessedMessage(Base):
    """Архив ID всех обработанных/удалённых сообщений для дедупликации."""

    __tablename__ = "processed_message"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)