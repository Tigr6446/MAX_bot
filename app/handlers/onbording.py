"""
Онбординг пользователя в MAX через FSM.
Собирает регион, город и категории интересов.

Валидация региона и города — через analyzer.detect_location().
"""

import logging

from maxapi.context import MemoryContext, State, StatesGroup
from maxapi.types import BotStarted, MessageCreated
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
    """
    Старт онбординга.
    Работает и для /start, и для кнопки «Начать» (BotStarted).
    """
    await context.set_state(Onboarding.waiting_for_region)

    if isinstance(event, BotStarted):
        # Кнопка «Начать» — нет event.message
        await event.bot.send_message(
            chat_id=event.chat_id,
            text=(
                "Привет! 👋\n\n"
                "Я помогу подбирать для тебя ивенты. "
                "Давай настроим профиль.\n\n"
                "📍 Напиши свой регион (например: Московская область):"
            ),
        )
    else:
        # Команда /start — есть event.message
        await event.message.answer(
            f"Привет, {event.from_user.first_name}! 👋\n\n"
            "Я помогу подбирать для тебя ивенты. "
            "Давай настроим профиль.\n\n"
            "📍 Напиши свой регион (например: Московская область):"
        )


async def process_region(event: MessageCreated, context: MemoryContext) -> None:
    """
    Получили регион → валидируем через анализатор.
    Если регион не распознан — просим ввести заново.
    """
    text = event.message.body.text if event.message.body else None
    if not text:
        return

    result = analyzer.detect_location(text)

    if not result["region"]:
        await event.message.answer(
            "🤔 Не смог распознать регион. Попробуй написать иначе:\n\n"
            "Например: Московская область, Республика Татарстан, "
            "Свердловская область"
        )
        return

    await context.update_data(region=result["region"])
    await context.set_state(Onboarding.waiting_for_city)
    await event.message.answer(
        f"📍 Регион: {result['region']}\n\n"
        "🏙 Теперь напиши свой город (например: Москва):"
    )


async def process_city(event: MessageCreated, context: MemoryContext) -> None:
    """
    Получили город → валидируем через анализатор.
    Проверяем, что город относится к указанному региону.
    """
    text = event.message.body.text if event.message.body else None
    if not text:
        return

    data = await context.get_data()
    saved_region = data.get("region")

    result = analyzer.detect_location(text)

    if not result["city"]:
        await event.message.answer(
            "🤔 Не смог распознать город. Попробуй написать иначе:\n\n"
            "Например: Москва, Казань, Екатеринбург"
        )
        return

    # Гео-конфликт: в тексте и регион, и город, но они не совпадают
    if result["conflict"]:
        await event.message.answer(
            f"⚠️ {result['error_msg']}\n\n"
            f"Ты указал регион: {saved_region}\n"
            "Уточни город или напиши /start заново."
        )
        return

    # В тексте указан город из другого региона
    if result["region"] and result["region"] != saved_region:
        await event.message.answer(
            f"⚠️ Город {result['city']} относится к региону "
            f"{result['region']}, а не к {saved_region}.\n\n"
            "Уточни город или напиши /start заново."
        )
        return

    await context.update_data(city=result["city"])
    await context.set_state(Onboarding.waiting_for_categories)
    await event.message.answer(
        f"🏙 Город: {result['city']}\n\n"
        "🎯 Последний шаг! Напиши категории, которые тебя интересуют, "
        "через запятую (или выбери что-то одно):\n\n"
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