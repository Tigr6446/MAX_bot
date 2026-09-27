"""
Онбординг пользователя в MAX через FSM.
Собирает регион, город и категории интересов.
"""

import logging

from maxapi.types import BotStarted
from maxapi.context import MemoryContext, State, StatesGroup
from maxapi.types import MessageCreated
from sqlalchemy.dialects.postgresql import insert

from app.Analyzer.analyzer import analyzer
from app.database.model_3 import AsyncSessionLocal, User

logger = logging.getLogger(__name__)


class Onboarding(StatesGroup):
    """Состояния онбординга."""
    waiting_for_region = State()
    waiting_for_city = State()
    waiting_for_categories = State()


async def cmd_start(event, context: MemoryContext) -> None:
    """Старт онбординга: работает и для /start, и для кнопки «Начать»."""
    await context.set_state(Onboarding.waiting_for_region)

    # Определяем, откуда пришло событие
    if isinstance(event, BotStarted):
        # Кнопка «Начать» — нет event.message
        await event.bot.send_message(
            chat_id=event.chat_id,
            text=(
                f"Привет! 👋\n\n"
                "Я помогу подбирать для тебя ивенты. "
                "Давай настроим профиль.\n\n"
                "📍 Напиши свой регион (например: Московская область):"
            ),
        )
    else:
        # Команда /start — есть event.message
        await event.message.answer(
            f"Привет, {event.from_user.first_name}! 👋\n\n"
            "📍 Напиши свой регион (например: Московская область):"
        )


async def process_region(event: MessageCreated, context: MemoryContext) -> None:
    """Получили регион → спрашиваем город."""
    text = event.message.body.text if event.message.body else None
    if not text:
        return

    await context.update_data(region=text.strip())
    await context.set_state(Onboarding.waiting_for_city)
    await event.message.answer(
        "Супер! 🏙 Теперь напиши свой город (например: Москва):"
    )


async def process_city(event: MessageCreated, context: MemoryContext) -> None:
    """Получили город → спрашиваем категории."""
    text = event.message.body.text if event.message.body else None
    if not text:
        return

    await context.update_data(city=text.strip())
    await context.set_state(Onboarding.waiting_for_categories)
    await event.message.answer(
        "Отлично! Последний шаг 🎯\n"
        "Напиши категории, кторые тебя интересуют через запятую (или выбери что-то одно):\n\n"
        "Например: волонтёрство, наука, культура, тренинги"
    )


async def process_categories(event: MessageCreated, context: MemoryContext) -> None:
    """Получили категории → сохраняем в БД."""
    text = event.message.body.text if event.message.body else None
    if not text:
        return

    data = await context.get_data()
    raw_interests = text.split(",")
    detected = set()

    for interest in raw_interests:
        category = analyzer.analyze_topic(interest)
        if category:
            detected.add(category)

    if not detected:
        await event.message.answer(
            "Не понял интересы 🤔 Попробуй иначе "
            "(например: наука, спорт, выставки, приюты):"
        )
        return

    categories_str = ",".join(detected)
    user_id = event.from_user.user_id

    async with AsyncSessionLocal() as session:
        stmt = insert(User).values(
            id=user_id,
            region=data.get("region"),
            city=data.get("city"),
            categories=categories_str,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "region": data.get("region"),
                "city": data.get("city"),
                "categories": categories_str,
            },
        )
        await session.execute(stmt)
        await session.commit()

    await event.message.answer(
        "✅ Профиль настроен!\n\n"
        f"📍 Регион: {data.get('region')}\n"
        f"🏙 Город: {data.get('city')}\n"
        f"🎯 Интересы: {categories_str}\n\n"
        "Теперь я буду помогать тебе с поиском мероприятий!"
    )

    await context.clear()