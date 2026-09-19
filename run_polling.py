import asyncio
import logging

from maxapi import Bot, Dispatcher
from maxapi.filters.command import CommandStart
from maxapi.types import MessageCreated

from app.config import settings
from app.handlers.start import cmd_start

logging.basicConfig(level=logging.INFO)

bot = Bot(settings.max_bot_token)
dp = Dispatcher()
dp.message_created(CommandStart())(cmd_start)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())