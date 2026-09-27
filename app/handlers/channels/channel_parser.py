"""
Парсер каналов MAX от лица пользовательского аккаунта.
Собирает посты из указанных каналов, прогоняет через анализатор
и сохраняет в БД. После работы объект самоудаляется.
"""

import asyncio
import logging

from pymax import (
    ConsoleQrHandler,
    ExtraConfig,
    QrAuthFlow,
    SyncOverrides,
    WebClient,
)
from sqlalchemy import select

from app.Analyzer.analyzer import analyzer
from app.database.model_1 import ParsedMessage, async_session

logger = logging.getLogger(__name__)


class ChannelParser:
    """
    Парсер каналов MAX.

    Жизненный цикл:
        parser = ChannelParser()
        await parser.run(channels=[-79132920662146])
        # объект дальше не нужен — уйдёт в GC
    """

    def __init__(self, work_dir: str = "cache"):
        # Папка, где PyMax хранит сессию (SQLite)
        self.work_dir = work_dir

        # QR-авторизация через консоль.
        # Если сессия уже сохранена — QR не понадобится.
        flow = QrAuthFlow(ConsoleQrHandler())

        # WebClient с принудительным полным sync чатов.
        # Без SyncOverrides(chats_sync=-1) PyMax вернёт chats=0.
        self.client = WebClient(
            auth_flow=flow,
            work_dir=work_dir,
            session_name="web.db",
            extra_config=ExtraConfig(
                sync=SyncOverrides(chats_sync=-1),
            ),
        )

    async def run(self, channels: list[int], limit: int = 25) -> None:
        """
        Полный цикл парсера: логин → парсинг → анализ → БД → закрытие.

        channels — список chat_id каналов (числа).
        limit — сколько последних постов тянуть из каждого канала.
        """
        # PyMax.start() не возвращает управление — он живёт в фоне,
        # слушая события. Поэтому запускаем его как отдельную задачу.
        start_task = asyncio.create_task(self.client.start())

        # Даём клиенту подключиться и залогиниться
        await asyncio.sleep(5)

        saved_total = 0
        skipped_total = 0

        # Идём по каналам по очереди
        for i, chat_id in enumerate(channels):
            try:
                # Тянем историю канала
                history = await self.client.fetch_history(
                    chat_id=chat_id,
                    backward=limit,
                )
            except Exception as e:
                logger.exception("Ошибка парсинга канала %s: %s", chat_id, e)
                continue

            # Открываем сессию БД на канал
            async with async_session() as session:
                for msg in history:
                    # Пропускаем посты без текста
                    if not msg.text:
                        continue

                    # Прогоняем через эвристический анализатор
                    category = analyzer.analyze(msg.text)
                    if not category:
                        continue

                    # --- ДЕДУПЛИКАЦИЯ ---
                    # Проверяем, есть ли уже запись с таким message_id
                    existing = await session.execute(
                        select(ParsedMessage).where(
                            ParsedMessage.message_id == str(msg.id)
                        )
                    )
                    if existing.scalar_one_or_none():
                        skipped_total += 1
                        continue

                    # --- СОХРАНЕНИЕ ---
                    session.add(ParsedMessage(
                        message_id=str(msg.id),
                        message_text=msg.text,
                        category=category,
                    ))
                    saved_total += 1

                await session.commit()

            logger.info("Канал %s обработан", chat_id)

            # Пауза между каналами (кроме последнего),
            # чтобы не долбить API MAX
            if i < len(channels) - 1:
                await asyncio.sleep(2)

        logger.info(
            "Итого: сохранено %d, пропущено дубликатов %d",
            saved_total, skipped_total,
        )

        # Останавливаем клиент и подчищаем фоновую задачу
        await self.client.stop()
        start_task.cancel()