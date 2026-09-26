from contextlib import asynccontextmanager

from fastapi import FastAPI
from maxapi import Dispatcher, Router
from maxapi.filters.command import Command
from maxapi.webhook.fastapi import FastAPIMaxWebhook
from maxapi import Bot

from app.config import settings
from app.database.model_1 import init_db
from app.handlers.CommandsUser import handle_user_command
from app.handlers.start import cmd_start

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with webhook.lifespan(app):
        yield

dp = Dispatcher()
router = Router()
bot = Bot(settings.max_bot_token)

router.message_created(Command("start"))(cmd_start)
router.message_created()(handle_user_command)

dp.include_routers(router)

# Создаём вебхук-интеграцию
webhook = FastAPIMaxWebhook(
    dp=dp,
    bot=bot,
    secret=settings.webhook_secret,
)

app = FastAPI(lifespan=lifespan)

# Подключаем вебхук к приложению
webhook.setup(app, path="/webhook")