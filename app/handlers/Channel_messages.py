"""
Модуль парсинга сообщений из каналов MAX.
"""

import logging

from maxapi.types import MessageCreated

from app.config import settings
from app.HeuristicAnalyzer import analyzer
from app.database import async_session
from app.database import ParsedMessage
from app.main import bot


logger = logging.getLogger()


async def handle_channel_message(message: MessageCreated):
    """
    Ловит сообщения из канала, анализирует текст эвристикой,
    пересылает оригинал в ЛС и сохраняет запись в БД.
    """

    # ─── 1. Текст ───
    text = message.body.text if message.body and message.body.text else None

    # ─── 2. Эвристика ───
    category = analyzer.analyze(text) if text else None
    category_label = (
        f"🎯 Категория: {category}" if category
        else "❓ Категория: не определена"
    )

    # ─── 3. Проверка получателя ───
    if not settings.MY_USER_ID:
        logger.warning("MY_USER_ID не задан в .env — пересылка пропущена")
        return

    # ─── 4. Пересылка оригинала в ЛС ───
    try:
        await message.forward(user_id=settings.MY_USER_ID)
        logger.info(
            "Сообщение переслано. Категория: %s",
            category or "не определена"
        )
    except Exception as e:
        logger.exception("Не удалось переслать: %s", e)
        return

    # ─── 5. Подпись с категорией ───
    try:
        await bot.send_message(
            chat_id=settings.MY_USER_ID,
            text=category_label,
        )
    except Exception as e:
        logger.exception("Не удалось отправить подпись: %s", e)

    # ─── 6. Сохранение в БД ───
    if category:
        try:
            channel_id = str(
                getattr(message.recipient, "chat_id", None)
                or getattr(getattr(message, "chat", None), "chat_id", "unknown")
            )

            async with async_session() as session:
                session.add(ParsedMessage(
                    channel_id=channel_id,
                    message_text=text or "[медиа без текста]",
                    category=category,
                ))
                await session.commit()
            logger.info("Запись сохранена в БД: %s", category)
        except Exception as e:
            logger.exception("Ошибка сохранения в БД: %s", e)
