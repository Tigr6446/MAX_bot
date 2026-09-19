import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from maxapi import Bot, Dispatcher
from maxapi.filters.command import CommandStart
from maxapi.types import MessageCreated

BOT_TOKEN = os.environ["MAX_BOT_TOKEN"]
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message_created(CommandStart())
async def cmd_start(event: MessageCreated):
    await event.message.answer(
        "Привет! Я бот для поиска событий. "
        "Скоро научусь присылать тебе волонтёрства, спорт и другие ивенты."
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Здесь позже инициализируем БД
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "healthy", "bot": "t277_hakaton_max_bot"}

# Вебхук от MAX
from maxapi.webhook.fastapi import FastAPIMaxWebhook
webhook = FastAPIMaxWebhook(dp, bot, path="/webhook", secret=os.environ["WEBHOOK_SECRET"])
app.include_router(webhook.router)