import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete
from app.database.model_1 import ParsedMessage, async_session

logger = logging.getLogger(__name__)

# Интервал проверки: 6 часов (в секундах)
LIBRARIAN_INTERVAL = 21600 

async def clean_expired_events() -> None:
    # Удаляет устаревшие события и посты без даты старше 5 дней
    now = datetime.now(timezone.utc)
    five_days_ago = now - timedelta(days=5)
    
    # Даем событию полностью пройти (удаляем на следующий день)
    yesterday = now - timedelta(days=1)

    async with async_session() as session:
        try:
            # Удаляем посты БЕЗ даты окончания, которым больше 5 дней с момента парсинга
            result_no_date = await session.execute(
                delete(ParsedMessage).where(
                    ParsedMessage.event_date.is_(None),
                    ParsedMessage.created_at < five_days_ago
                )
            )
            
            # даляем посты с датой окончания, которая уже ПРОШЛА (учитывая весь день события)
            result_expired = await session.execute(
                delete(ParsedMessage).where(
                    ParsedMessage.event_date.isnot(None),
                    ParsedMessage.event_date < yesterday 
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
    # Бесконечный фоновый цикл Библиотекаря
    logger.info("Фоновая задача 'Библиотекарь' запущена")
    while True:
        await clean_expired_events()
        await asyncio.sleep(LIBRARIAN_INTERVAL)