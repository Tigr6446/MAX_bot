"""
Загрузчик событий с dobro.ru в БД (таблица web_events).
Запускает парсер, читает JSON, валидирует и сохраняет.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.database.model_1 import async_session
from app.database.model_2 import WebEvent

logger = logging.getLogger(__name__)


def _extract_event_date(text: str) -> datetime | None:
    """
    Пытается вытащить дату окончания события из текста.
    Поддерживает форматы:
      - "9 августа – 31 октября 2026"
      - "23 – 30 сентября 2026"
      - "4 октября 2026"
    """
    if not text:
        return None

    months = {
        "января": 1, "январь": 1, "февраля": 2, "февраль": 2,
        "марта": 3, "март": 3, "апреля": 4, "апрель": 4,
        "мая": 5, "май": 5, "июня": 6, "июнь": 6,
        "июля": 7, "июль": 7, "августа": 8, "август": 8,
        "сентября": 9, "сентябрь": 9, "октября": 10, "октябрь": 10,
        "ноября": 11, "ноябрь": 11, "декабря": 12, "декабрь": 12,
    }
    month_pattern = "|".join(months.keys())

    # "9 августа – 31 октября 2026" → берём вторую дату (конец)
    m = re.search(
        rf'(\d{{1,2}})\s+(?:{month_pattern})\s*[–-]\s*'
        rf'(\d{{1,2}})\s+({month_pattern})\s+(\d{{4}})',
        text, re.IGNORECASE
    )
    if m:
        day, month_word, year = int(m.group(2)), m.group(3).lower(), int(m.group(4))
        try:
            return datetime(year, months[month_word], day)
        except ValueError:
            pass

    # "23 – 30 сентября 2026"
    m = re.search(
        rf'(\d{{1,2}})\s*[–-]\s*(\d{{1,2}})\s+({month_pattern})\s+(\d{{4}})',
        text, re.IGNORECASE
    )
    if m:
        day, month_word, year = int(m.group(2)), m.group(3).lower(), int(m.group(4))
        try:
            return datetime(year, months[month_word], day)
        except ValueError:
            pass

    # "4 октября 2026"
    m = re.search(
        rf'(\d{{1,2}})\s+({month_pattern})\s+(\d{{4}})',
        text, re.IGNORECASE
    )
    if m:
        day, month_word, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        try:
            return datetime(year, months[month_word], day)
        except ValueError:
            pass

    return None


def _clean_social_links(links: list[str]) -> list[str]:
    """Оставляет только ссылки на реальные соцсети."""
    social_domains = ["vk.com", "vk.ru", "t.me", "max.ru", "ok.ru", "dzen.ru"]
    result = []
    for url in links:
        if not url:
            continue
        if any(d in url for d in social_domains):
            result.append(url)
    return result


async def parse_and_load(
    region: str,
    city: str,
    category: str = "volunteering",
) -> int:
    """
    Запускает парсер dobro.ru для указанного города,
    читает JSON, валидирует и заливает в web_events.
    Возвращает количество добавленных записей.
    """
    # Импорт внутри функции — чтобы не тянуть Playwright при старте
    from app.handlers.web_parsing.parserCards import main as run_parser

    logger.info("Запускаем парсер dobro.ru: %s / %s", region, city)
    try:
        await asyncio.to_thread(run_parser, region, city)
    except Exception as e:
        logger.exception("Парсер упал: %s", e)
        return 0

    # Читаем JSON
    safe_city = city.replace(" ", "_").replace("/", "_")
    json_path = Path(f"dobro_{safe_city}.json")
    if not json_path.exists():
        logger.warning("JSON не найден: %s", json_path)
        return 0

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            events = json.load(f)
    except Exception as e:
        logger.exception("Ошибка чтения JSON: %s", e)
        return 0

    logger.info("Прочитано событий из JSON: %d", len(events))

    added = 0
    skipped = 0
    async with async_session() as session:
        for e in events:
            url = e.get("url")
            if not url:
                continue

            # Проверка на дубликат
            existing = await session.execute(
                select(WebEvent).where(WebEvent.url == url)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            # Собираем текст
            title = (e.get("title") or "").strip()
            description = (e.get("description") or "").strip()
            text = f"{title}\n\n{description}".strip()[:4000]

            # Дата окончания
            event_date = _extract_event_date(e.get("main_info", ""))

            session.add(WebEvent(
                url=url,
                title=title[:500] if title else None,
                message_text=text,
                region=e.get("region") or region,
                city=e.get("city") or city,
                category=category,
                event_date=event_date,
            ))
            added += 1

        await session.commit()

    logger.info("Загружено в web_events: %d, пропущено дубликатов: %d", added, skipped)
    return added