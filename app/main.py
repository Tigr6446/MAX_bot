from contextlib import asynccontextmanager

from fastapi import FastAPI
from maxapi import Dispatcher, Router
from maxapi.filters.command import Command

from app.bot_instance import bot
from app.database import init_db
from app.handlers.channel import handle_channel_message
from app.handlers.start import cmd_start


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


dp = Dispatcher()
router = Router()

# Регистрация хендлеров
router.message_created(Command("start"))(cmd_start)
router.message_created()(handle_channel_message)

dp.include_routers(router)

app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "bot": "t277_hakaton_max_bot"}