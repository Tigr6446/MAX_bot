from maxapi.types import MessageCreated


async def cmd_start(event: MessageCreated) -> None:
    await event.message.answer(
        "Привет! Я бот для поиска событий.\n\n"
        "Скоро научусь присылать тебе волонтёрства, спорт и другие ивенты "
        "по твоим интересам."
    )