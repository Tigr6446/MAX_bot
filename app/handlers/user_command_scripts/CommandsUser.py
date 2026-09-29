"""
Обработчик пользовательских команд в ЛС бота.
Бот работает ТОЛЬКО в личных сообщениях.
"""

import asyncio
import logging
from typing import Optional

from maxapi.types import MessageCreated

from app.Analyzer.analyzer import analyzer
from app.database.requests import get_upcoming_events, count_all_events

logger = logging.getLogger(__name__)

# Хранилище контекста пользователей:
# {user_id: {"category": Optional[str], "offset": int, "title": str}}
user_sessions: dict[int, dict] = {}

PAGE_SIZE = 10


async def handle_user_command(event: MessageCreated) -> None:
    """Основной обработчик сообщений пользователя."""
    if not event.from_user:
        return

    text = event.message.body.text if event.message.body else None
    if not text:
        return

    user_id = event.from_user.user_id
    normalized = text.strip().lower()

    # --- "Да" ---
    if normalized in ["да", "д", "давай", "ага", "еще", "ещё", "покажи еще", "продолжай"]:
        if user_id in user_sessions:
            session = user_sessions[user_id]
            session["offset"] += PAGE_SIZE
            await _send_next_page(event, user_id, session)
            return
        else:
            await event.message.answer(
                "У вас нет активного поиска. Напишите категорию "
                "(например, «Спорт») или «Все мероприятия»."
            )
            return

    # --- "Нет" ---
    if normalized in ["нет", "н", "не", "стоп", "хватит", "отмена"]:
        if user_id in user_sessions:
            del user_sessions[user_id]
            await event.message.answer(
                "Хорошо! Если захотите найти что-то ещё — просто напишите."
            )
            return

    # --- Категория ---
    detected_category = analyzer.analyze(text)

    if detected_category:
        user_sessions[user_id] = {
            "category": detected_category,
            "offset": 0,
            "title": f"Мероприятия по категории: {detected_category}",
        }
        await _send_next_page(event, user_id, user_sessions[user_id])
        return

    # --- Все мероприятия ---
    all_triggers = [
        "мероприятия", "события", "все мероприятия",
        "все события", "все предстоящие", "покажи все", "выведи все"
    ]
    if any(tr in normalized for tr in all_triggers):
        user_sessions[user_id] = {
            "category": None,
            "offset": 0,
            "title": "Все предстоящие мероприятия",
        }
        await _send_next_page(event, user_id, user_sessions[user_id])
        return

    # --- Дефолт ---
    if user_id in user_sessions:
        await event.message.answer(
            "Извиняюсь, не совсем понял вас.\n\n"
            "• Напишите «Да», чтобы показать следующие 10 мероприятий.\n"
            "• Или введите новый запрос."
        )
    else:
        await event.message.answer(
            "Извиняюсь, я не понял запрос. Напишите его в свободной форме:\n"
            "• «Выведи все мероприятия»\n"
            "• «Мероприятия по Пушкинской карте»\n"
            "• «Культура и кино» или «Театр»\n"
            "• «Мастер-классы»\n"
            "• «Спортивные соревнования»"
        )


async def _send_next_page(event: MessageCreated, user_id: int, session: dict) -> None:
    """Запрос в БД и формирование ответа."""
    category = session["category"]
    offset = session["offset"]
    title = session["title"]

    events = await get_upcoming_events(
        category=category, limit=PAGE_SIZE, offset=offset
    )

    # Если пусто и это первая страница
    if not events and offset == 0:
        total = await count_all_events()

        if total == 0:
            await event.message.answer("⏳ Подождите немного, ищу мероприятия...")
            try:
                from app.handlers.channels import ChannelParser
                from app.config import settings

                channels = [
                    int(x.strip())
                    for x in settings.parser_channels.split(",")
                    if x.strip()
                ]

                if channels:
                    parser = ChannelParser()
                    await parser.run(channels=channels, limit=25)
                    del parser
                    logger.info("Парсер запущен для пользователя %s", user_id)
            except Exception as e:
                logger.exception("Ошибка парсера: %s", e)
                await event.message.answer(
                    f"❌ Не удалось запустить парсер: {type(e).__name__}"
                )
                user_sessions.pop(user_id, None)
                return

            events = await get_upcoming_events(
                category=category, limit=PAGE_SIZE, offset=offset
            )
        else:
            await event.message.answer(
                f"😔 Пока нет мероприятий по категории «{title}».\n\n"
                "Попробуй позже или выбери другую категорию."
            )
            user_sessions.pop(user_id, None)
            return

    if not events:
        if offset == 0:
            await event.message.answer(
                f"😔 Пока нет мероприятий по категории «{title}»."
            )
        else:
            await event.message.answer("Больше мероприятий по этому запросу нет")
        user_sessions.pop(user_id, None)
        return

    # Группировка по категориям (только посты с категорией)
    grouped: dict[str, list] = {}
    for item in events:
        if not item.category:
            continue
        grouped.setdefault(item.category, []).append(item)

    if not grouped:
        await event.message.answer(
            f"😔 Пока нет мероприятий по категории «{title}»."
        )
        user_sessions.pop(user_id, None)
        return

    await event.message.answer(f"📌 {title}\n")

    # Показываем заголовок категории только если их несколько
    show_category_headers = len(grouped) > 1

    counter = offset + 1
    for cat_key, items in grouped.items():
        if show_category_headers:
            await event.message.answer(f"🎯 {cat_key}")
        for item in items:
            await event.message.answer(f"{counter}. {item.message_text}", format="markdown")
            counter += 1
            await asyncio.sleep(0.3)

    if len(events) < PAGE_SIZE:
        user_sessions.pop(user_id, None)
        await event.message.answer("Это все мероприятия по данному запросу.")
    else:
        await event.message.answer("Нужны ли ещё мероприятия? (Да / Нет)")