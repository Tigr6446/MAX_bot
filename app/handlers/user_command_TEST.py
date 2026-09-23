"""
Обработчик пользовательских команд в ЛС бота.
Сейчас тут только тестовая команда для запуска парсера каналов.
"""

import logging

from maxapi.types import MessageCreated

from app.config import settings
from app.handlers.channels import ChannelParser

logger = logging.getLogger(__name__)

# Точная фраза, на которую реагирует бот (для теста)
TRIGGER_PHRASE = "Нужны мероприятия из каналов"


async def handle_user_command(event: MessageCreated) -> None:
    """
    Ловит команды пользователя в ЛС.
    Пока реагирует только на тестовую фразу TRIGGER_PHRASE.
    """
    # Достаём текст сообщения
    text = event.message.body.text if event.message.body else None
    if not text:
        return

    # Нормализуем: убираем лишние пробелы, приводим к нижнему регистру
    normalized = text.strip().lower()

    # Проверяем на тестовую фразу
    if normalized == TRIGGER_PHRASE.lower():
        await _run_parser_and_reply(event)
        return

    # На всё остальное — заготовка для будущих команд
    # (позже тут будет поиск по БД и фильтрация)


async def _run_parser_and_reply(event: MessageCreated) -> None:
    """
    Запускает парсер каналов и отвечает пользователю.
    """
    # Сначала сообщаем, что работаем — парсинг может занять время
    await event.message.answer("⏳ Запускаю парсинг каналов, подожди...")

    # Читаем список chat_id из .env (строка "123,456" → [123, 456])
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
        parser = ChannelParser(phone=settings.parser_phone)
        await parser.run(channels=channels)
        del parser

        await event.message.answer(
            "✅ Парсинг завершён. Мероприятия сохранены в БД."
        )
        logger.info("Парсер успешно запущен пользователем %s", event.from_user.user_id)

    except Exception as e:
        logger.exception("Ошибка парсера: %s", e)
        await event.message.answer(
            f"❌ Ошибка при парсинге: {type(e).__name__}"
        )