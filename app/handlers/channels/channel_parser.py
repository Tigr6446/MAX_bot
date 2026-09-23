"""
Парсер каналов MAX от лица пользовательского аккаунта.
Собирает посты из указанных каналов, прогоняет через анализатор
и сохраняет в БД. После работы объект самоудаляется.
"""

import logging

from pymax import Client

from app.analyzer import analyzer
from app.database.model_1 import ParsedMessage, async_session

logger = logging.getLogger(__name__)


class ChannelParser:
    """
    Парсер каналов MAX.

    Жизненный цикл:
        parser = ChannelParser(phone="+79990000000")
        await parser.run(channels=[123456789, 987654321])
        # объект дальше не нужен — уйдёт в GC
    """

    def __init__(self, phone: str, work_dir: str = "cache"):
        # Номер телефона аккаунта, от которого парсим
        self.phone = phone
        # Папка, где PyMax хранит сессию (SQLite)
        self.work_dir = work_dir
        # Клиент PyMax. Сессия сохранится в parser.db —
        # при повторных запусках SMS-код уже не спросит
        self.client = Client(
            phone=phone,
            work_dir=work_dir,
            session_name="parser.db",
        )

    async def run(self, channels: list[int], limit: int = 50) -> None:
        """
        Полный цикл парсера: логин → парсинг → анализ → БД → закрытие.

        channels — список chat_id каналов (числа).
        limit — сколько последних постов тянуть из каждого канала.
        """

        # Подключаемся к MAX под пользователем.
        # При первом запуске PyMax попросит SMS-код в консоль.
        await self.client.start()

        saved_total = 0

        # Идём по каждому каналу по очереди
        for chat_id in channels:
            try:
                # Получаем историю канала (limit последних постов)
                history = await self.client.fetch_history(
                    chat_id=chat_id,
                    backward=limit,
                )
            except Exception as e:
                # Если канал недоступен — логируем и идём к следующему
                logger.exception("Ошибка парсинга канала %s: %s", chat_id, e)
                continue

            # Открываем сессию БД один раз на канал
            async with async_session() as session:
                for msg in history:
                    # Пропускаем посты без текста (медиа, стикеры и т.п.)
                    if not msg.text:
                        continue

                    # Прогоняем текст через эвристический анализатор.
                    # Если категория не определена — пост не сохраняем.
                    category = analyzer.analyze(msg.text)
                    if not category:
                        continue

                    # Сохраняем пост в БД
                    session.add(ParsedMessage(
                        message_text=msg.text,
                        category=category,
                    ))
                    saved_total += 1

                # Фиксируем все вставки по каналу
                await session.commit()

            logger.info("Канал %s обработан", chat_id)

        logger.info("Всего сохранено записей: %d", saved_total)

        # Закрываем соединение, чтобы освободить ресурсы.
        # После этого объект можно смело удалять.
        await self.client.stop()