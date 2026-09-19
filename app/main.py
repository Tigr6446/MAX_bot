from contextlib import asynccontextmanager

from fastapi import FastAPI
from maxapi import Bot, Dispatcher
from maxapi.filters.command import CommandStart

from app.config import settings
from app.database import init_db
from app.handlers.start import cmd_start


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создаём таблицы при старте
    await init_db()
    yield


bot = Bot(settings.max_bot_token)
dp = Dispatcher()
dp.message_created(CommandStart())(cmd_start)


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "bot": "t277_hakaton_max_bot"}