import logging
import re
from maxapi.context import MemoryContext, State, StatesGroup
from maxapi.types import MessageCreated
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.Analyzer.analyzer import analyzer
from app.database.model_3 import AsyncSessionLocal, User
from app.handlers.onbording import Onboarding

logger = logging.getLogger(__name__)


class SettingsStates(StatesGroup):
    waiting_for_action = State()
    changing_region = State()
    changing_city = State()
    confirm_city_change = State()
    changing_categories = State()


# Общий список слов для выхода/отмены во всех состояниях
EXIT_WORDS = ["отмен", "стоп", "хватит", "закр", "выйти", "назад"]


async def get_user_profile(user_id: int) -> User | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def check_settings_intent(event: MessageCreated, context: MemoryContext) -> bool:
    text = event.message.body.text if event.message.body and event.message.body.text else ""
    text = text.strip().lower()
    action_pattern = r"(измени|поменя|смени|обнови|друг)"
    
    # Проверка желания сменить регион
    if re.search(rf"{action_pattern}.*регион", text):
        await context.set_state(SettingsStates.changing_region)
        await event.message.answer("📍 Напиши новый регион (например: Московская область) или напиши СТОП/ОТМЕНА для выхода:")
        return True
        
    # Проверка желания сменить город
    if re.search(rf"{action_pattern}.*город", text):
        await context.set_state(SettingsStates.changing_city)
        await event.message.answer("🏙 Напиши новый город (например: Казань) или напиши СТОП/ОТМЕНА для выхода:")
        return True
        
    # Проверка желания сменить категории
    if re.search(rf"{action_pattern}.*(категори|интерес)", text):
        await context.set_state(SettingsStates.changing_categories)
        await event.message.answer(
            "🎯 Напиши новые категории через запятую "
            "(наука, тренинги, форумы, волонтёрство, культура, мероприятия по пушкинской карте) "
            "или напиши СТОП/ОТМЕНА для выхода:"
        )
        return True
        
    # Проверка вызова меню настроек
    if re.search(r"(настройк|профиль|меню)", text):
        await cmd_settings(event, context)
        return True
        
    return False


async def cmd_settings(event: MessageCreated, context: MemoryContext) -> None:
    user_id = event.from_user.user_id
    user = await get_user_profile(user_id)

    if not user:
        await event.message.answer("Ты ещё не настроил профиль! Нажми /start, чтобы начать.")
        return

    await context.set_state(SettingsStates.waiting_for_action)
    await event.message.answer(
        f"⚙️ ТЕКУЩИЙ ПРОФИЛЬ:\n\n"
        f"📍 Регион: {user.region or 'не указан'}\n"
        f"🏙 Город: {user.city or 'не указан'}\n"
        f"🎯 Интересы: {user.categories or 'не указаны'}\n\n"
        "Что именно ты хочешь изменить?\n"
        "1. Напиши РЕГИОН (или «изменить регион»)\n"
        "2. Напиши ГОРОД (или «изменить город»)\n"
        "3. Напиши КАТЕГОРИИ (или «изменить интересы»)\n"
        "4. Напиши ЗАНОВО (пройти всю настройку с нуля)\n"
        "5. Или напиши ОТМЕНА, СТОП, ХВАТИТ, ЗАКРЫТЬ для выхода."
    )


async def process_settings_action(event: MessageCreated, context: MemoryContext) -> None:
    text = event.message.body.text.strip().lower() if event.message.body and event.message.body.text else ""

    # Выход из настроек
    if any(word in text for word in EXIT_WORDS):
        await context.clear()
        await event.message.answer("❌ Настройки закрыты.")
        return

    # Полный перезапуск онбординга
    if "занов" in text or "сначала" in text:
        await context.set_state(Onboarding.waiting_for_region)
        await event.message.answer(
            "🔄 Начинаем настройку заново.\n\n"
            "📍 Напиши свой регион (например: Московская область):"
        )
        return

    # Переход к смене региона
    if "регион" in text:
        await context.set_state(SettingsStates.changing_region)
        await event.message.answer("📍 Напиши новый регион:")
        return

    # Переход к смене города
    if "город" in text:
        await context.set_state(SettingsStates.changing_city)
        await event.message.answer("🏙 Напиши новый город:")
        return

    # Переход к смене категорий
    if "категори" in text or "интерес" in text:
        await context.set_state(SettingsStates.changing_categories)
        await event.message.answer(
            "🎯 Напиши новые категории через запятую "
            "(наука, тренинги, форумы, волонтёрство, культура, мероприятия по пушкинской карте, спорт):"
        )
        return

    await event.message.answer(
        "🤔 Не понял команду. Выбери, что изменить: РЕГИОН, ГОРОД, КАТЕГОРИИ, ЗАНОВО или СТОП."
    )


async def save_new_region(event: MessageCreated, context: MemoryContext) -> None:
    text = event.message.body.text if event.message.body and event.message.body.text else ""
    if not text:
        return

    if any(word in text.lower() for word in EXIT_WORDS):
        await context.clear()
        await event.message.answer("❌ Настройки закрыты.")
        return

    result = analyzer.detect_location(text)
    if not result["region"]:
        await event.message.answer("🤔 Не смог распознать регион. Попробуй ещё раз (или напиши СТОП для выхода):")
        return

    new_region = result["region"]
    user_id = event.from_user.user_id

    # Сохраняем регион и сбрасываем старый город
    async with AsyncSessionLocal() as session:
        stmt = (
            insert(User)
            .values(id=user_id, region=new_region, city=None)
            .on_conflict_do_update(
                index_elements=["id"], 
                set_={"region": new_region, "city": None}
            )
        )
        await session.execute(stmt)
        await session.commit()

    # Заставляем юзера сразу ввести новый город
    await context.set_state(SettingsStates.changing_city)
    await event.message.answer(
        f"✅ Регион изменен на: {new_region}.\n\n"
        f"Так как регион поменялся, твой старый город сброшен.\n"
        f"🏙 Теперь напиши свой новый город (который находится в этом регионе):"
    )


async def save_new_city(event: MessageCreated, context: MemoryContext) -> None:
    text = event.message.body.text if event.message.body and event.message.body.text else ""
    if not text:
        return

    if any(word in text.lower() for word in EXIT_WORDS):
        await context.clear()
        await event.message.answer("❌ Настройки закрыты.")
        return

    user_id = event.from_user.user_id
    user = await get_user_profile(user_id)
    saved_region = user.region if user else None

    result = analyzer.detect_location(text)
    if not result["city"]:
        await event.message.answer("🤔 Не смог распознать город. Попробуй ещё раз (или напиши СТОП для выхода):")
        return

    new_city = result["city"]
    new_region = result["region"]

    # Если регион города не совпадает с сохраненным — запрашиваем подтверждение
    if saved_region and new_region and new_region != saved_region:
        await context.update_data(pending_city=new_city, pending_region=new_region)
        await context.set_state(SettingsStates.confirm_city_change)
        await event.message.answer(
            f"⚠️ Внимание: город {new_city} относится к региону «{new_region}», "
            f"а у тебя сейчас установлен регион «{saved_region}».\n\n"
            f"Вы уверены, что хотите поменять настройки и обновить И ГОРОД, И РЕГИОН? (Да / Нет)"
        )
        return

    update_data = {"city": new_city}
    if not saved_region and new_region:
        update_data["region"] = new_region

    async with AsyncSessionLocal() as session:
        stmt = (
            insert(User)
            .values(id=user_id, **update_data)
            .on_conflict_do_update(index_elements=["id"], set_=update_data)
        )
        await session.execute(stmt)
        await session.commit()

    await context.clear()
    await event.message.answer(f"✅ Город успешно изменен на: {new_city} 🎉")


async def confirm_city_change_action(event: MessageCreated, context: MemoryContext) -> None:
    text = event.message.body.text.strip().lower() if event.message.body and event.message.body.text else ""
    
    if any(word in text for word in EXIT_WORDS):
        await context.clear()
        await event.message.answer("❌ Настройки закрыты.")
        return

    # Подтверждение смены региона и города
    if text in ["да", "д", "уверен", "ага", "давай"]:
        data = await context.get_data()
        new_city = data.get("pending_city")
        new_region = data.get("pending_region")
        user_id = event.from_user.user_id

        update_data = {"city": new_city, "region": new_region}
        
        async with AsyncSessionLocal() as session:
            stmt = (
                insert(User)
                .values(id=user_id, **update_data)
                .on_conflict_do_update(index_elements=["id"], set_=update_data)
            )
            await session.execute(stmt)
            await session.commit()

        await context.clear()
        await event.message.answer(
            f"✅ Профиль полностью обновлён!\n\n"
            f"📍 Новый регион: {new_region}\n"
            f"🏙 Новый город: {new_city} 🎉"
        )
    elif text in ["нет", "н", "не"]:
        await context.clear()
        await event.message.answer("❌ Изменение отменено. Оставляем всё как было.")
    else:
        await event.message.answer("Пожалуйста, ответьте «Да» или «Нет» (или напишите СТОП для отмены).")


async def save_new_categories(event: MessageCreated, context: MemoryContext) -> None:
    text = event.message.body.text if event.message.body and event.message.body.text else ""
    if not text:
        return

    if any(word in text.lower() for word in EXIT_WORDS):
        await context.clear()
        await event.message.answer("❌ Настройки закрыты.")
        return

    raw_interests = text.split(",")
    detected = set()

    for interest in raw_interests:
        category = analyzer.analyze_topic(interest.strip())
        if category:
            detected.add(category)

    if not detected:
        await event.message.answer(
            "🤔 Не понял интересы. Попробуй написать категории через запятую "
            "(наука, тренинги и мастер классы, форумы, волонтёрство, культура, мероприятия по пушкинской карте, спорт):"
        )
        return

    categories_str = ",".join(detected)
    user_id = event.from_user.user_id

    async with AsyncSessionLocal() as session:
        stmt = (
            insert(User)
            .values(id=user_id, categories=categories_str)
            .on_conflict_do_update(index_elements=["id"], set_={"categories": categories_str})
        )
        await session.execute(stmt)
        await session.commit()

    await context.clear()
    await event.message.answer(f"✅ Интересы успешно обновлены: {categories_str} 🎉")