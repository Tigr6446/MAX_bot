"""
Парсер каналов MAX от лица пользовательского аккаунта.
Собирает посты из указанных каналов, прогоняет через анализатор
и сохраняет в БД. После работы объект самоудаляется.
"""

import asyncio
import logging
from datetime import datetime

from pymax import (
    ConsoleQrHandler,
    ExtraConfig,
    QrAuthFlow,
    SyncOverrides,
    WebClient,
)
from pymax.types.domain.enums import LinkType
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

    @staticmethod
    def _extract_real_message(msg):
        """
        Если сообщение пересланное — берём оригинал внутри link.message.
        Иначе — возвращаем само сообщение.
        """
        try:
            if msg.link and msg.link.type == LinkType.FORWARD:
                return msg.link.message
        except Exception:
            pass
        return msg

    async def run(self, channels: list[int], limit: int = 15) -> None:
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
        garbage_total = 0

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
                    # Если сообщение пересланное — работаем с оригиналом
                    real_msg = self._extract_real_message(msg)

                    real_id = getattr(real_msg, "id", None)
                    if not real_id:
                        continue

                    # Текст из оригинала
                    text = getattr(real_msg, "text", None)
                    if not text:
                        continue

                    # Прогоняем сообщение через полный эвристический анализатор
                    analysis = analyzer.analyze_message(text)

                    if not analysis["is_event"]:
                        garbage_total += 1
                        logger.debug(
                            "Пост %s пропущен: %s",
                            real_msg.id, analysis["reason"],
                        )
                        continue

                    # Достаём категорию
                    category = analysis["category"]
                    if not category:
                        garbage_total += 1
                        logger.debug(
                            "Пост %s пропущен: категория не определена",
                            real_msg.id,
                        )
                        continue

                    # Преобразуем строковую дату "YYYY-MM-DD" обратно в datetime
                    event_date = (
                        datetime.strptime(analysis["date"], "%Y-%m-%d")
                        if analysis["date"]
                        else None
                    )

                    # --- ССЫЛКА НА ОРИГИНАЛ ---
                    # Ищем в elements ссылку вида max.ru/канал/код_поста
                    post_url = None
                    elements = getattr(real_msg, "elements", None) or []
                    for el in elements:
                        if getattr(el, "type", None) == "LINK":
                            attrs = getattr(el, "attributes", None)
                            url = getattr(attrs, "url", None) if attrs else None
                            if not url or "max.ru/" not in url:
                                continue

                            # Разбираем URL: max.ru/<segment1>/<segment2>
                            after_domain = url.split("max.ru/", 1)[1].strip("/")
                            parts = after_domain.split("/")

                            # Ссылка на пост: ровно 2 сегмента (канал/код)
                            if len(parts) == 2 and parts[0] and parts[1]:
                                post_url = url
                                break

                    # --- ДЕДУПЛИКАЦИЯ ---
                    existing = await session.execute(
                        select(ParsedMessage).where(
                            ParsedMessage.message_id == str(real_id)
                        )
                    )
                    if existing.scalar_one_or_none():
                        skipped_total += 1
                        continue

                    # --- СОХРАНЕНИЕ ---
                    session.add(ParsedMessage(
                        message_id=str(real_id),
                        message_text=text,
                        category=category,
                        post_url=post_url,
                        event_date=event_date,
                    ))
                    saved_total += 1

                await session.commit()

            logger.info("Канал %s обработан", chat_id)

            # Пауза между каналами (кроме последнего),
            # чтобы не долбить API MAX
            if i < len(channels) - 1:
                await asyncio.sleep(2)

        logger.info(
            "Итого: сохранено %d, пропущено дубликатов %d, отсеяно мусора %d",
            saved_total, skipped_total, garbage_total,
        )

        # Останавливаем клиент и подчищаем фоновую задачу
        await self.client.stop()
        start_task.cancel()