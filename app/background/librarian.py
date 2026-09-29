import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import delete
from app.database.model_1 import ParsedMessage, async_session

logger = logging.getLogger(__name__)

# --- Конфигурация Библиотекаря ---
LIBRARIAN_INTERVAL = 120  # Интервал проверки (в секундах)
NO_DATE_TTL = timedelta(minutes=2)  # Время жизни постов БЕЗ даты (для тестов: 2 минуты)


async def clean_expired_events() -> None:
    """Удаляет устаревшие события и посты без даты из базы данных."""
    # Используем местное время без tzinfo, чтобы оно совпадало с created_at в БД
    now = datetime.now()
    
    cutoff_no_date = now - NO_DATE_TTL
    # Для сравнения строковых дат YYYY-MM-DD берем вчерашний день строкой
    yesterday_str = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")

    async with async_session() as session:
        try:
            # 1. Удаляем посты БЕЗ даты, созданные более NO_DATE_TTL назад
            result_no_date = await session.execute(
                delete(ParsedMessage).where(
                    ParsedMessage.event_date.is_(None),
                    ParsedMessage.created_at < cutoff_no_date
                )
            )
            
            # 2. Удаляем посты с датой, которая уже прошла
            result_expired = await session.execute(
                delete(ParsedMessage).where(
                    ParsedMessage.event_date.isnot(None),
                    ParsedMessage.event_date < yesterday_str
                )
            )
            
            await session.commit()
            
            deleted_count = (result_no_date.rowcount or 0) + (result_expired.rowcount or 0)
            if deleted_count > 0:
                logger.info("Библиотекарь очистил базу: удалено устаревших записей: %d", deleted_count)
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