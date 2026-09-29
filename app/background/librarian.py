import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database.model_1 import ParsedMessage, async_session
from app.database.model_4 import ProcessedMessage

logger = logging.getLogger(__name__)

# --- Конфигурация Библиотекаря ---
LIBRARIAN_INTERVAL = 120  # Интервал проверки базы (в секундах)
NO_DATE_TTL = timedelta(minutes=2)  # Время жизни постов БЕЗ даты (для тестов: 2 минуты, для прода: timedelta(days=5))


async def clean_expired_events() -> None:
    """
    Ищет устаревшие события и посты без даты,
    заносит их message_id в архив ProcessedMessage
    и удаляет из активной таблицы ParsedMessage.
    """
    now = datetime.now()
    cutoff_no_date = now - NO_DATE_TTL
    yesterday = now - timedelta(days=1)   # datetime, не строка

    async with async_session() as session:
        try:
            # 1. Выбираем все посты, у которых истек срок жизни
            query = select(ParsedMessage).where(
                (ParsedMessage.event_date.is_(None) & (ParsedMessage.created_at < cutoff_no_date)) |
                (ParsedMessage.event_date.isnot(None) & (ParsedMessage.event_date < yesterday))
            )
            result = await session.execute(query)
            expired_messages = result.scalars().all()

            if expired_messages:
                # 2. Переносим ID в архив и удаляем из рабочей таблицы
                for msg in expired_messages:
                    await session.merge(ProcessedMessage(message_id=msg.message_id))
                    await session.delete(msg)

                await session.commit()
                logger.info(
                    "Библиотекарь очистил базу: заархивировано и удалено записей: %d",
                    len(expired_messages),
                )
            else:
                logger.debug("Библиотекарь проверил базу: удалять нечего")

        except Exception as e:
            logger.exception("Ошибка в работе Библиотекаря: %s", e)
            await session.rollback()


async def librarian_loop() -> None:
    """Бесконечный фоновый цикл Библиотекаря."""
    logger.info("Фоновая задача 'Библиотекарь' запущена")
    while True:
        await clean_expired_events()
        await asyncio.sleep(LIBRARIAN_INTERVAL)