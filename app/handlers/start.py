from maxapi.types import MessageCreated


async def cmd_start(event: MessageCreated) -> None:
    await event.message.answer(
        "Привет! Я бот для поиска событий.\n\n"
        "я буду присылать тебе волонтёрства, спорт и другие ивенты."
    )