"""
Обработчик сообщений из каналов MAX.
Анализирует текст, пересылает админу и сохраняет в БД.
"""

import logging

from maxapi.types import MessageCreated

from app.analyzer import analyzer
from app.bot_instance import bot
from app.config import settings
from app.database import ParsedMessage, async_session

logger = logging.getLogger(__name__)


async def handle_channel_message(event: MessageCreated) -> None:
    
    logger.info(
        "Пришло сообщение: chat=%r, chat_id=%r, text=%r",
        event.chat,
        getattr(event.chat, "chat_id", None) or getattr(event.chat, "id", None),
        event.message.body.text if event.message.body else None,
    )


    # 1. Текст сообщения
    text = event.message.body.text if event.message.body else None

    # 2. Категория
    category = analyzer.analyze(text)
    category_label = (
        f"🎯 Категория: {category}" if category
        else "❓ Категория: не определена"
    )

    # 3. Пересылаем админу (вручную, т.к. forward_message в API нет)
    try:
        await bot.send_message(
            chat_id=settings.my_user_id,
            text=(
                f"📩 Новое сообщение в канале\n\n"
                f"{text or '[медиа без текста]'}\n\n"
                f"{category_label}"
            ),
        )
        logger.info("Сообщение переслано админу. Категория: %s", category)
    except Exception as e:
        logger.exception("Не удалось переслать: %s", e)

    # 4. Сохраняем в БД (только если категория определена)
    if category:
        try:
            channel_id = str(
                getattr(event.chat, "chat_id", None)
                or getattr(event.chat, "id", "unknown")
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