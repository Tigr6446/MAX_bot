from maxapi import Router, Message, F
from app.database.model_3 import AsyncSessionLocal, User
from sqlalchemy.dialects.postgresql import insert
from app.Analyzer.analyzer import analyzer

router = Router()

# Простейшее in-memory хранилище состояний
# Формат: {user_id: {"step": "step_name", "region": "...", "city": "..."}}
user_fsm: dict[int, dict] = {}

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    #Приветствуем и запрошиваем регион
    user_id = message.from_user.id
    
    #Инициализируем состояние пользователя
    user_fsm[user_id] = {"step": "waiting_for_region"}

    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я твой умный помощник. Чтобы я мог подбирать для тебя самые крутые ивенты, "
        "волонтёрские проекты и научные встречи, давай немного настроим профиль.\n\n"
        "📍 **Напиши свой регион** (например: Московская область):"
    )

@router.message(F.text & ~F.text.startswith("/"))
async def process_onboarding(message: Message):
    #Единый обработчик шагов заполнения профиля
    user_id = message.from_user.id
    state = user_fsm.get(user_id)

    if not state:
        return #Игнор, если пользователь не в процессе регистрации

    step = state.get("step")

    #Получили регион, спрашиваем город
    if step == "waiting_for_region":
        state["region"] = message.text.strip()
        state["step"] = "waiting_for_city"
        await message.answer("Супер! 🏙 **Теперь напиши свой город** (например: Москва):")

    #Получили город, спрашиваем категории
    elif step == "waiting_for_city":
        state["city"] = message.text.strip()
        state["step"] = "waiting_for_categories"
        await message.answer(
            "Отлично! Последний шаг 🎯\n"
            "Напиши категории, которые тебе интересны (через запятую):\n\n"
            "Например: волонтёрство, наука, культурные мероприятия, треннинги"
        )

    #Получили категории, сохраняем в БД
    elif step == "waiting_for_categories":
        raw_interests = message.text.split(",")
        detected_categories = set()

        #Прогоняем каждое слово через эвристический анализатор
        for interest in raw_interests:
            category = analyzer.analyze_topic(interest)
            if category:
                detected_categories.add(category)

        #Случай, если анализатор ничего не понял
        if not detected_categories:
            await message.answer(
                "Я не совсем понял твои интересы 🤔\n"
                "Попробуй написать иначе (например: наука, спорт, выставки, приюты):"
            )
            return

        state["categories"] = ",".join(detected_categories)
        
        #Асинхронное сохранение в БД
        async with AsyncSessionLocal() as session:
            stmt = insert(User).values(
                id=user_id,
                region=state["region"],
                city=state["city"],
                categories=state["categories"]
            ).on_conflict_do_update(
                index_elements=['id'],
                set_={
                    'region': state["region"],
                    'city': state["city"],
                    'categories': state["categories"]
                }
            )
            await session.execute(stmt)
            await session.commit()

        #Делаем подтверждение
        await message.answer(
            "✅ **Профиль успешно настроен!**\n\n"
            f"📍 Регион: {state['region']}\n"
            f"🏙 Город: {state['city']}\n"
            f"🎯 Интересы: {state['categories']}\n\n"
            "Теперь я буду присылать события специально для тебя! "
            "Чтобы изменить настройки, просто напиши /start"
        )
        
        #Очищаем состояние, чтобы бот вернулся в обычный режим работы
        user_fsm.pop(user_id, None)