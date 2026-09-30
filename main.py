import asyncio

from contextlib import asynccontextmanager

from fastapi import FastAPI

from maxapi import Dispatcher, Router, Bot
from maxapi.filters.command import Command
from maxapi.filters.state import StateFilter
from maxapi.webhook.fastapi import FastAPIMaxWebhook

from app.config import settings

import app.database.model_1
import app.database.model_3
import app.database.model_4

from app.database.model_1 import init_db

from app.handlers.user_command_scripts.CommandsUser import handle_user_command
from app.handlers.user_command_scripts.onbording import (
    Onboarding,
    cmd_start,
    process_region,
    process_city,
    process_categories,
)
from app.handlers.user_command_scripts.Settings import (
    SettingsStates,
    cmd_settings,
    check_settings_intent,
    process_settings_action,
    save_new_region,
    save_new_city,
    confirm_city_change_action,
    save_new_categories,
)

from app.background.notifier import parser_loop
from app.background.librarian import librarian_loop

dp = Dispatcher()
router = Router()
bot = Bot(settings.max_bot_token)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    
    # Запускаем фоновую задачу парсера
    parser_task = asyncio.create_task(parser_loop(bot))
    # Запускаем библиотекаря
    librarian_task = asyncio.create_task(librarian_loop())
    
    async with webhook.lifespan(app):
        yield
    
    # При завершении — отменяем задачу
    parser_task.cancel()
    librarian_task.cancel() # Вырубаем библиотекаря

# --- Онбординг ---
router.bot_started()(cmd_start)
router.message_created(Command("start"))(cmd_start)
router.message_created(StateFilter(Onboarding.waiting_for_region))(process_region)
router.message_created(StateFilter(Onboarding.waiting_for_city))(process_city)
router.message_created(StateFilter(Onboarding.waiting_for_categories))(process_categories)

# --- Настройки ---
router.message_created(Command("settings"))(cmd_settings)
router.message_created(Command("setting"))(cmd_settings)
router.message_created(StateFilter(SettingsStates.waiting_for_action))(process_settings_action)
router.message_created(StateFilter(SettingsStates.changing_region))(save_new_region)
router.message_created(StateFilter(SettingsStates.changing_city))(save_new_city)
router.message_created(StateFilter(SettingsStates.confirm_city_change))(confirm_city_change_action)
router.message_created(StateFilter(SettingsStates.changing_categories))(save_new_categories)


# --- Обёртка для обычных команд ---
async def pre_user_command(event, context):
    """Проверяет настройки, иначе — обычные команды."""
    # Игнорируем посты из каналов (from_user = None)
    if not event.from_user:
        return
    
    is_settings_intent = await check_settings_intent(event, context)
    if is_settings_intent:
        return
    await handle_user_command(event)


router.message_created()(pre_user_command)

dp.include_routers(router)

webhook = FastAPIMaxWebhook(
    dp=dp,
    bot=bot,
    secret=settings.webhook_secret,
)

app = FastAPI(lifespan=lifespan)
webhook.setup(app, path="/webhook")