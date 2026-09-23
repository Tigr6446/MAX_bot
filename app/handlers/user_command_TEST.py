"""
Обработчик пользовательских команд в ЛС бота.
Бот работает ТОЛЬКО в личных сообщениях.
"""

import logging

from maxapi.types import MessageCreated

from app.config import settings
from app.handlers.channels import ChannelParser

logger = logging.getLogger(__name__)

# Триггерная фраза для запуска парсера (для теста)
TRIGGER_PHRASE = "нужны мероприятия из каналов"


async def handle_user_command(event: MessageCreated) -> None:
    """
    Ловит команды пользователя в ЛС бота.
    Пока реагирует только на TRIGGER_PHRASE.
    """
    text = event.message.body.text if event.message.body else None
    if not text:
        return

    normalized = text.strip().lower()

    if normalized == TRIGGER_PHRASE:
        await _run_parser_and_reply(event)
        return

    # Заготовка для будущих команд (поиск по БД и т.п.)


async def _run_parser_and_reply(event: MessageCreated) -> None:
    """
    Запускает парсер каналов и отвечает пользователю.
    """
    await event.message.answer("⏳ Запускаю парсинг каналов, подожди...")

    # Читаем список chat_id из .env: "123,456" → [123, 456]
    channels = [
        int(x.strip())
        for x in settings.parser_channels.split(",")
        if x.strip()
    ]

    if not channels:
        await event.message.answer(
            "❌ Список каналов пуст. Проверь PARSER_CHANNELS в .env."
        )
        return

    try:
        # Создаём парсер, запускаем, удаляем
        parser = ChannelParser()
        await parser.run(channels=channels, limit=10)
        del parser

        await event.message.answer(
            "✅ Парсинг завершён. Мероприятия сохранены в БД."
        )
        logger.info(
            "Парсер запущен пользователем %s",
            event.from_user.user_id,
        )
    except Exception as e:
        logger.exception("Ошибка парсера: %s", e)
        await event.message.answer(
            f"❌ Ошибка при парсинге: {type(e).__name__}"
        )