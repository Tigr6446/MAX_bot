from contextlib import asynccontextmanager

from fastapi import FastAPI
from maxapi import Dispatcher, Router
from maxapi.filters.command import Command
from maxapi.webhook.fastapi import FastAPIMaxWebhook

from app.bot_instance import bot
from app.config import settings
from app.database.model_1 import init_db
from app.handlers.channel import handle_channel_message
from app.handlers.start import cmd_start


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


dp = Dispatcher()
router = Router()

router.message_created(Command("start"))(cmd_start)
router.message_created()(handle_channel_message)

dp.include_routers(router)

# Создаём вебхук-интеграцию
webhook = FastAPIMaxWebhook(
    dp=dp,
    bot=bot,
    secret=settings.webhook_secret,
)

app = FastAPI(lifespan=webhook.lifespan)

# Подключаем вебхук к приложению
webhook.setup(app, path="/webhook")