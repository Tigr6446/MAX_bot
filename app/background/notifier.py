"""
Фоновая задача: периодический опрос каналов и рассылка новых мероприятий.
"""

import asyncio
import logging

from sqlalchemy import select, func

from app.config import settings
from app.database.model_1 import ParsedMessage, async_session
from app.database.model_3 import User, AsyncSessionLocal

logger = logging.getLogger(__name__)

# Интервал опроса в секундах
POLL_INTERVAL = 300  # 5 минут


async def _get_max_message_id() -> int:
    """Возвращает максимальный id в parsed_message."""
    async with async_session() as session:
        result = await session.execute(
            select(func.max(ParsedMessage.id))
        )
        return result.scalar_one() or 0


async def _get_new_events(last_id: int) -> list[ParsedMessage]:
    """Возвращает новые записи (id > last_id)."""
    async with async_session() as session:
        result = await session.execute(
            select(ParsedMessage).where(ParsedMessage.id > last_id)
        )
        return list(result.scalars().all())


async def _get_all_chat_ids() -> list[int]:
    """Возвращает все chat_id из users (только не None)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User.chat_id).where(User.chat_id.isnot(None))
        )
        return [row[0] for row in result.all()]


async def _notify_users(bot, events: list[ParsedMessage]) -> None:
    """Рассылает новые мероприятия, сгруппированные по категориям."""
    chat_ids = await _get_all_chat_ids()
    if not chat_ids:
        logger.warning("Нет пользователей для рассылки")
        return

    CATEGORY_TITLES = {
        "volunteering": "Волонтёрство",
        "forum": "Форумы и конференции",
        "science": "Наука и образование",
        "sport": "Спорт",
        "culture": "Культура и искусство",
        "workshop": "Мастер-классы и воркшопы",
        "pushkin_card": "Пушкинская карта",
    }

    # 1. Группируем события по категориям
    grouped: dict[str, list[ParsedMessage]] = {}
    for event in events:
        cat_key = event.category or "other"
        grouped.setdefault(cat_key, []).append(event)

    # 2. Для каждой категории формируем одно сообщение
    for cat_key, cat_events in grouped.items():
        cat_label = CATEGORY_TITLES.get(cat_key, "Без категории")

        # Заголовок
        lines = [f"🔔 Новые мероприятия: {cat_label}\n"]

        # Мероприятия
        for i, event in enumerate(cat_events, start=1):
            text_preview = event.message_text[:300]
            if len(event.message_text) > 300:
                text_preview += "..."
            lines.append(f"{i}. {text_preview}")

        message_text = "\n\n".join(lines)

        # 3. Отправляем каждому пользователю
        for chat_id in chat_ids:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                )
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.exception(
                    "Не удалось отправить уведомление chat_id=%s: %s",
                    chat_id, e,
                )

async def parser_loop(bot) -> None:
    """
    Фоновая задача: сначала парсит, потом спит 5 минут.
    Цикл бесконечный.
    """
    logger.info("Фоновая задача парсера запущена")

    while True:
        try:
            # 1. Запоминаем максимальный id ДО парсинга
            last_id = await _get_max_message_id()

            # 2. Запускаем парсер
            from app.handlers.channels import ChannelParser

            channels = [
                int(x.strip())
                for x in settings.parser_channels.split(",")
                if x.strip()
            ]

            if not channels:
                logger.warning("PARSER_CHANNELS пуст, парсер не запускается")
            else:
                parser = ChannelParser()
                await parser.run(channels=channels, limit=5)
                del parser

                # 3. Смотрим, что нового
                new_events = await _get_new_events(last_id)

                if new_events:
                    logger.info("Найдено %d новых мероприятий", len(new_events))
                    await _notify_users(bot, new_events)
                else:
                    logger.info("Новых мероприятий нет")

        except Exception as e:
            logger.exception("Ошибка в parser_loop: %s", e)

        # 4. Спим 5 минут
        await asyncio.sleep(POLL_INTERVAL)