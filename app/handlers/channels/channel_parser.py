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
from sqlalchemy import select

from app.Analyzer.analyzer import analyzer
from app.database import ParsedMessage, ProcessedMessage, async_session

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
            link = getattr(msg, "link", None)
            if link and getattr(link, "message", None):
                return link.message
        except Exception:
            pass
        return msg

    @staticmethod
    def _inject_links_into_text(real_msg) -> str:
        """
        Вшивает ссылки обратно в анкоры в формате markdown:
        [анкор](url).

        Работает по позициям from/length из elements.
        Если URL уже есть в тексте — пропускает (дубликат).
        Заменяет с конца, чтобы позиции не сдвигались.
        """
        text = getattr(real_msg, "text", None) or ""
        elements = getattr(real_msg, "elements", None) or []

        # Собираем LINK-элементы с позициями и URL
        links: list[tuple[int, int, str]] = []
        for el in elements:
            if getattr(el, "type", None) != "LINK":
                continue

            from_pos = getattr(el, "from", None)
            length = getattr(el, "length", None)
            attrs = getattr(el, "attributes", None)
            url = getattr(attrs, "url", None) if attrs else None

            if from_pos is None or length is None or not url:
                continue

            # Пропускаем, если URL уже есть в тексте (обычная ссылка)
            if url in text:
                continue

            links.append((from_pos, length, url))

        if not links:
            return text

        # Сортируем по позиции в обратном порядке — замена не сдвигает индексы
        links.sort(key=lambda x: x[0], reverse=True)

        result = text
        for from_pos, length, url in links:
            # Страховка от выхода за границы
            if from_pos < 0 or from_pos + length > len(result):
                continue

            anchor = result[from_pos:from_pos + length]

            if not anchor.strip():
                continue

            # Экранируем квадратные скобки в анкоре
            anchor_safe = anchor.replace("[", "\\[").replace("]", "\\]")

            replacement = f"[{anchor_safe}]({url})"
            result = result[:from_pos] + replacement + result[from_pos + length:]

        return result

    async def run(self, channels: list[int], limit: int = 15) -> None:
        """
        Полный цикл парсера: логин → парсинг → анализ → БД → закрытие.

        channels — список chat_id каналов (числа).
        limit — сколько последних постов тянуть из каждого канала.
        """
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

                    # ID сообщения
                    real_id = getattr(real_msg, "id", None)
                    if not real_id:
                        continue

                    str_real_id = str(real_id)

                    # --- ДЕДУПЛИКАЦИЯ (Проверка активной БД и архива) ---
                    in_active = await session.execute(
                        select(ParsedMessage.message_id).where(
                            ParsedMessage.message_id == str_real_id
                        )
                    )
                    in_processed = await session.execute(
                        select(ProcessedMessage.message_id).where(
                            ProcessedMessage.message_id == str_real_id
                        )
                    )

                    if in_active.scalar_one_or_none() or in_processed.scalar_one_or_none():
                        skipped_total += 1
                        continue

                    # Текст из оригинала
                    text = getattr(real_msg, "text", None)
                    if not text:
                        continue

                    # Полный анализ: категория, локация, дата, is_event
                    analysis = analyzer.analyze_message(text)

                    if not analysis["is_event"]:
                        garbage_total += 1
                        # Сохраняем мусор в архив, чтобы не анализировать его снова
                        await session.merge(ProcessedMessage(message_id=str_real_id))
                        logger.debug(
                            "Пост %s пропущен и заархивирован: %s",
                            str_real_id, analysis["reason"],
                        )
                        continue

                    # Категория
                    category = analysis["category"]
                    if not category:
                        garbage_total += 1
                        # Сохраняем мусор в архив
                        await session.merge(ProcessedMessage(message_id=str_real_id))
                        logger.debug(
                            "Пост %s пропущен и заархивирован: категория не определена",
                            str_real_id,
                        )
                        continue

                    # Дата события
                    event_date = (
                        datetime.strptime(analysis["date"], "%Y-%m-%d")
                        if analysis["date"]
                        else None
                    )

                    # --- ВШИТЫЕ ССЫЛКИ (анкоры) ---
                    full_text = self._inject_links_into_text(real_msg)

                    # --- СОХРАНЕНИЕ ---
                    session.add(ParsedMessage(
                        message_id=str_real_id,
                        message_text=full_text,
                        category=category,
                        event_date=event_date,
                    ))
                    saved_total += 1

                await session.commit()

            logger.info("Канал %s обработан", chat_id)

            # Пауза между каналами (кроме последнего)
            if i < len(channels) - 1:
                await asyncio.sleep(2)

        logger.info(
            "Итого: сохранено %d, пропущено дубликатов %d, отсеяно мусора %d",
            saved_total, skipped_total, garbage_total,
        )

        # Останавливаем клиент и подчищаем фоновую задачу
        await self.client.stop()
        start_task.cancel()