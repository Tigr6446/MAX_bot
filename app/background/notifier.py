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
POLL_INTERVAL = 300  # 5 минут - 300 сек


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


async def _get_users_with_categories() -> list[tuple[int, set[str]]]:
    """
    Возвращает список (chat_id, set(категорий)) для всех пользователей
    с заполненным chat_id.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User.chat_id, User.categories).where(User.chat_id.isnot(None))
        )
        users: list[tuple[int, set[str]]] = []
        for chat_id, categories in result.all():
            if not categories:
                cats: set[str] = set()
            else:
                cats = {c.strip() for c in categories.split(",") if c.strip()}
            users.append((chat_id, cats))
        return users


async def _notify_users(bot, events: list[ParsedMessage]) -> None:
    """Рассылает новые мероприятия по категориям пользователей."""
    users = await _get_users_with_categories()
    if not users:
        logger.warning("Нет пользователей для рассылки")
        return

    # Группируем события по категориям
    grouped: dict[str, list[ParsedMessage]] = {}
    for event in events:
        if not event.category:
            continue
        grouped.setdefault(event.category, []).append(event)

    if not grouped:
        logger.info("Нет событий с категориями для рассылки")
        return

    # Каждому пользователю — только его категории
    for chat_id, user_cats in users:
        # Если у пользователя не заданы категории — пропускаем
        if not user_cats:
            continue

        # Собираем события, подходящие под интересы юзера
        matching: list[ParsedMessage] = []
        for cat_key, cat_events in grouped.items():
            if cat_key in user_cats:
                matching.extend(cat_events)

        if not matching:
            continue

        # Формируем текст: по категориям, с разделителями
        lines: list[str] = ["🔔 Новые мероприятия для тебя\n"]
        for cat_key in user_cats:
            cat_events = grouped.get(cat_key)
            if not cat_events:
                continue
            lines.append("-"*45)
            lines.append(f"🎯 {cat_key}")
            for i, event in enumerate(cat_events, start=1):
                lines.append(f"{i}. {event.message_text}")

        message_text = "\n\n".join(lines)

        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                format="markdown",
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
        # 1. Спим 5 минут
        await asyncio.sleep(POLL_INTERVAL)
        
        try:
            # 2. Запоминаем максимальный id ДО парсинга
            last_id = await _get_max_message_id()

            # 3. Запускаем парсер
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

                # 4. Смотрим, что нового
                new_events = await _get_new_events(last_id)

                if new_events:
                    logger.info("Найдено %d новых мероприятий", len(new_events))
                    await _notify_users(bot, new_events)
                else:
                    logger.info("Новых мероприятий нет")

        except Exception as e:
            logger.exception("Ошибка в parser_loop: %s", e)

        