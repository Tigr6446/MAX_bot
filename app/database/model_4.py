
"""ћодель дл€ архивации обработанных сообщений."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.model_1 import Base


class ProcessedMessage(Base):
    """јрхив ID всех обработанных/удалЄнных сообщений дл€ дедупликации."""

    __tablename__ = "processed_message"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)