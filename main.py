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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with webhook.lifespan(app):
        yield


dp = Dispatcher()  # storage=MemoryContext по умолчанию
router = Router()
bot = Bot(settings.max_bot_token)

# Онбординг
router.message_created(Command("start"))(cmd_start)
router.message_created(StateFilter(Onboarding.waiting_for_region))(process_region)
router.message_created(StateFilter(Onboarding.waiting_for_city))(process_city)
router.message_created(StateFilter(Onboarding.waiting_for_categories))(process_categories)

# Обычные команды — последними
router.message_created()(handle_user_command)

dp.include_routers(router)

webhook = FastAPIMaxWebhook(
    dp=dp,
    bot=bot,
    secret=settings.webhook_secret,
)

app = FastAPI(lifespan=lifespan)
webhook.setup(app, path="/webhook")