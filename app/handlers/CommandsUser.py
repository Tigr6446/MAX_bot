"""
Обработчик пользовательских команд в ЛС бота.
Бот работает ТОЛЬКО в личных сообщениях.
"""
import logging
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
    user_id = event.message.from_user.id if event.message.from_user else event.recipient.id
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
    """
    category = session["category"]
    offset = session["offset"]
    title = session["title"]

    #Запрос в БД с учётом offset
    events = await get_upcoming_events(category=category, limit=PAGE_SIZE, offset=offset)

    if not events:
        if offset == 0:
            await event.message.answer(f"<b>{title}</b>\n\nК сожалению, ничего не найдено.")
        else:
            await event.message.answer("Больше мероприятий по этому запросу нет")
        
        #Сбрасываем сессию, т.к. список закончился
        user_sessions.pop(user_id, None)
        return

    response_lines = [f"<b>{title}</b>\n"]
    for item in events:
        date_str = item.event_date.strftime("%d.%m.%Y %H:%M")
        line = f"• <b>{item.title}</b> — {date_str}"
        if getattr(item, "url", None):
            line += f"\n  Ссылка: {item.url}"
        response_lines.append(line)

    response_lines.append("\n<b>Нужны ли ещё мероприятия? (Да / Нет)</b>")

    await event.message.answer("\n\n".join(response_lines))