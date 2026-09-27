"""
Обработчик пользовательских команд в ЛС бота.
Бот работает ТОЛЬКО в личных сообщениях.
"""
import logging
import asyncio
from typing import Optional
from maxapi.types import MessageCreated
from app.Analyzer.analyzer import analyzer
from app.database.requests import get_upcoming_events

logger = logging.getLogger(__name__)

#Хранилище контекста пользователей: {user_id: {"category": Optional[str], "offset": int, "title": str}}
user_sessions: dict[int, dict] = {}
PAGE_SIZE = 10


async def handle_user_command(event: MessageCreated) -> None:
    """
    Основной обработчик сообщений пользователя.
    Поддерживает распознавание категорий и постраничный вывод (пагинацию) через диалог «Да / Нет».
    """
    text = event.message.body.text if event.message.body else None
    if not text:
        return

    #ID пользователя
    user_id = event.from_user.user_id
    normalized = text.strip().lower()

    #Проверка на согласие продолжить просмотр ("Да")
    if normalized in ["да", "д", "давай", "ага", "еще", "ещё", "покажи еще", "продолжай"]:
        if user_id in user_sessions:
            session = user_sessions[user_id]
            session["offset"] += PAGE_SIZE  # Сдвигаем выборку на следующие 10
            await _send_next_page(event, user_id, session)
            return
        else:
            await event.message.answer(
                "У вас нет активного поиска. Напишите категорию (например, «Спорт») или «Все мероприятия»."
            )
            return

    #Проверка на отказ от продолжения просмотра ("Нет")
    if normalized in ["нет", "н", "не", "стоп", "хватит", "отмена"]:
        if user_id in user_sessions:
            del user_sessions[user_id]
            await event.message.answer("Хорошо! Если захотите найти что-то ещё — просто напишите.")
            return

    #Распознавание категории через эвристический анализатор
    detected_category = analyzer.analyze(text)

    if detected_category:
        category_titles = {
            "volunteering": "Волонтёрство",
            "forum": "Форумы и конференции",
            "science": "Наука и образование",
            "sport": "Спорт",
            "culture": "Культура и искусство",
            "workshop": "Мастер-классы и воркшопы",
            "pushkin_card": "Пушкинская карта",
        }
        title = category_titles.get(detected_category, detected_category.capitalize())

        #Создаём новую сессию поиска (если была старая - перезапишется)
        user_sessions[user_id] = {
            "category": detected_category,
            "offset": 0,
            "title": f"Мероприятия по категории: {title}",
        }
        await _send_next_page(event, user_id, user_sessions[user_id])
        return

    #Проверка на вывод всех мероприятий без фильтра
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

    #Дефолтный ответ, если текст не распознан
    if user_id in user_sessions:
        await event.message.answer(
            "Извиняюсь, не совсем понял вас.\n\n"
            "• Напишите **«Да»**, чтобы показать следующие 10 мероприятий.\n"
            "• Или введите новый запрос (например: «Культура», «Спорт», «Все мероприятия»)."
        )
    else:
        await event.message.answer(
            "Извиняюсь, я не понял запрос. Напишите его в свободной форме пожалуйста, например:\n"
            "• «Выведи все мероприятия»\n"
            "• «Мероприятия по Пушкинской карте»\n"
            "• «Культура и кино» или «Театр»\n"
            "• «Мастер-классы»\n"
            "• «Спортивные соревнования»"
        )


async def _send_next_page(event: MessageCreated, user_id: int, session: dict) -> None:
    """
    Вспомогательная функция: делаем запрос в БД и формируем ответ.
    Если в БД пусто — запускаем парсер и пробуем снова.
    """
    category = session["category"]
    offset = session["offset"]
    title = session["title"]

    # Первый запрос в БД
    events = await get_upcoming_events(
        category=category, limit=PAGE_SIZE, offset=offset
    )

    # Если пусто и это первая страница — запускаем парсер
    if not events and offset == 0:
        await event.message.answer(
            "⏳ Подождите немного, ищу мероприятия..."
        )

        # Запускаем парсер
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
                await parser.run(channels=channels, limit=10)
                del parser
                logger.info("Парсер запущен для пользователя %s", user_id)
        except Exception as e:
            logger.exception("Ошибка парсера: %s", e)
            await event.message.answer(
                f"❌ Не удалось запустить парсер: {type(e).__name__}"
            )
            user_sessions.pop(user_id, None)
            return

        # Повторный запрос в БД после парсинга
        events = await get_upcoming_events(
            category=category, limit=PAGE_SIZE, offset=offset
        )

    # Если и после парсинга пусто
    if not events:
        if offset == 0:
            await event.message.answer(
                f"😔 По запросу «{title}» ничего не найдено."
            )
        else:
            await event.message.answer("Больше мероприятий по этому запросу нет")

        user_sessions.pop(user_id, None)
        return

    # Формируем сообщение с категорией
    await event.message.answer(f"📌 {title}\n")

    # Отправляем мероприятия по одному
    for i, item in enumerate(events, start=offset + 1):
        text_preview = item.message_text[:300]
        if len(item.message_text) > 300:
            text_preview += "..."

        cat_label = item.category or "без категории"
        await event.message.answer(
            f"{i}. [{cat_label}]\n\n{text_preview}"
        )
        await asyncio.sleep(0.3)  # пауза между сообщениями

    # Спрашиваем про следующую страницу
    await event.message.answer("Нужны ли ещё мероприятия? (Да / Нет)")