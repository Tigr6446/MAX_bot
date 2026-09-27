"""
Онбординг пользователя в MAX.
Собирает регион, город и категории интересов.
"""

import logging

from maxapi.types import MessageCreated
from sqlalchemy.dialects.postgresql import insert

from app.Analyzer.analyzer import analyzer
from app.database.model_3 import AsyncSessionLocal, User

logger = logging.getLogger(__name__)

# In-memory хранилище состояний онбординга
# {user_id: {"step": "...", "region": "...", "city": "..."}}
user_fsm: dict[int, dict] = {}


async def cmd_start(event: MessageCreated) -> None:
    """Приветствие и запрос региона."""
    user_id = event.from_user.user_id
    user_fsm[user_id] = {"step": "waiting_for_region"}

    await event.message.answer(
        f"Привет, {event.from_user.first_name}! 👋\n\n"
        "Я твой умный помощник. Чтобы подбирать для тебя ивенты, "
        "давай немного настроим профиль.\n\n"
        "📍 Напиши свой регион (например: Московская область):"
    )


async def process_onboarding(event: MessageCreated) -> None:
    """Обработчик шагов онбординга."""
    user_id = event.from_user.user_id
    state = user_fsm.get(user_id)

    if not state:
        return  # пользователь не в процессе онбординга

    text = event.message.body.text if event.message.body else None
    if not text:
        return

    step = state.get("step")

    if step == "waiting_for_region":
        state["region"] = text.strip()
        state["step"] = "waiting_for_city"
        await event.message.answer(
            "Супер! 🏙 Теперь напиши свой город (например: Москва):"
        )
        return

    if step == "waiting_for_city":
        state["city"] = text.strip()
        state["step"] = "waiting_for_categories"
        await event.message.answer(
            "Отлично! Последний шаг 🎯\n"
            "Напиши категории через запятую:\n\n"
            "Например: волонтёрство, наука, культура, тренинги"
        )
        return

    if step == "waiting_for_categories":
        raw_interests = text.split(",")
        detected = set()

        for interest in raw_interests:
            category = analyzer.analyze_topic(interest)
            if category:
                detected.add(category)

        if not detected:
            await event.message.answer(
                "Я не совсем понял интересы 🤔\n"
                "Попробуй иначе (например: наука, спорт, выставки, приюты):"
            )
            return

        state["categories"] = ",".join(detected)

        # Сохранение в БД
        async with AsyncSessionLocal() as session:
            stmt = insert(User).values(
                id=user_id,
                region=state["region"],
                city=state["city"],
                categories=state["categories"],
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "region": state["region"],
                    "city": state["city"],
                    "categories": state["categories"],
                },
            )
            await session.execute(stmt)
            await session.commit()

        await event.message.answer(
            "✅ Профиль настроен!\n\n"
            f"📍 Регион: {state['region']}\n"
            f"🏙 Город: {state['city']}\n"
            f"🎯 Интересы: {state['categories']}\n\n"
            "Теперь я буду присылать события для тебя!"
        )

        user_fsm.pop(user_id, None)
        return