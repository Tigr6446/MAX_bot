from contextlib import asynccontextmanager

from fastapi import FastAPI

from maxapi import Dispatcher, Router, Bot
from maxapi.filters.command import Command
from maxapi.filters.state import StateFilter
from maxapi.webhook.fastapi import FastAPIMaxWebhook

from app.config import settings
from app.database.model_1 import init_db
from app.handlers.CommandsUser import handle_user_command
from app.handlers.onbording import (
    Onboarding,
    cmd_start,
    process_region,
    process_city,
    process_categories,
)
from app.handlers.Settings import (
    SettingsStates,
    cmd_settings,
    check_settings_intent,
    process_settings_action,
    save_new_region,
    save_new_city,
    confirm_city_change_action,
    save_new_categories,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with webhook.lifespan(app):
        yield


dp = Dispatcher()
router = Router()
bot = Bot(settings.max_bot_token)

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