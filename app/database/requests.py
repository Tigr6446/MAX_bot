"""Запросы к БД для получения мероприятий."""

from sqlalchemy import select, desc, func

from app.database.model_1 import ParsedMessage, async_session


async def get_upcoming_events(
    category: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> list[ParsedMessage]:
    """
    Возвращает список мероприятий с пагинацией.

    category — фильтр по категории (None = все).
    limit — сколько записей вернуть.
    offset — с какой записи начать.
    """
    async with async_session() as session:
        query = select(ParsedMessage).order_by(desc(ParsedMessage.id))

        if category:
            query = query.where(ParsedMessage.category == category)

        query = query.limit(limit).offset(offset)

        result = await session.execute(query)
        return list(result.scalars().all())


async def count_all_events() -> int:
    """Возвращает общее количество мероприятий в БД."""
    async with async_session() as session:
        result = await session.execute(
            select(func.count(ParsedMessage.id))
        )
        return result.scalar_one()