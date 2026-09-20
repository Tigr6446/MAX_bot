from maxapi.types import MessageCreated


async def cmd_start(event: MessageCreated) -> None:
    await event.message.answer(
        "Привет! Я бот для поиска событий.\n\n"
        "Добавь меня в канал или чат с анонсами — "
        "я буду присылать тебе волонтёрства, спорт и другие ивенты."
    )