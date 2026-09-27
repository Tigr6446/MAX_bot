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
POLL_INTERVAL = 60  # 5 минут


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


async def _get_all_users() -> list[int]:
    """Возвращает всех user_id из users."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.id))
        return [row[0] for row in result.all()]


async def _notify_users(bot, events: list[ParsedMessage]) -> None:
    """Рассылает новые мероприятия всем пользователям."""
    user_ids = await _get_all_users()
    if not user_ids:
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

    for event in events:
        cat_label = CATEGORY_TITLES.get(event.category or "", "Мероприятие")
        text_preview = event.message_text[:300]
        if len(event.message_text) > 300:
            text_preview += "..."

        message_text = (
            f"🔔 Новое мероприятие!\n\n"
            f"🎯 {cat_label}\n\n"
            f"{text_preview}"
        )

        for user_id in user_ids:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                )
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.exception(
                    "Не удалось отправить уведомление пользователю %s: %s",
                    user_id, e,
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