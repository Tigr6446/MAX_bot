from sqlalchemy import BigInteger, String, ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from app.database.model_1 import Base
from app.database.model_1 import async_session as AsyncSessionLocal

from app.config import settings

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True) # id �����
    region: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    categories: Mapped[str | None] = mapped_column(String(255)) #�������� ��� ������ ����� ������� ��� ��������
