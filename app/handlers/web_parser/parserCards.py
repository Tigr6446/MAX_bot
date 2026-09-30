"""
Парсер карточек с dobro.ru.
Запускается через Playwright, собирает события для указанного города,
сохраняет в JSON.
"""

import json
import time
import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def open_city_modal(page) -> bool:
    """Открывает окно выбора города."""
    selectors = [
        "header button:has-text('Москва')",
        "header button:has-text('Казань')",
        "header button:has-text('Санкт-Петербург')",
        "header button:has(svg):near(:text('добро.рф'))",
        "button[data-slot='popover-anchor']",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                loc.click()
                print(f"[OK] Кликнули по кнопке города: {sel}")
                return True
        except Exception:
            continue
    return False


def select_city(page, city_name: str) -> bool:
    """Выбирает город через UI сайта."""
    print(f"[..] Выбираем город '{city_name}'...")

    if not open_city_modal(page):
        print("[ERR] Не нашли кнопку открытия окна города.")
        return False

    try:
        input_field = page.locator("input[placeholder='Введите название']").first
        input_field.wait_for(state="visible", timeout=10000)
    except Exception:
        print("[ERR] Поле 'Введите название' не появилось.")
        return False

    input_field.click()
    input_field.fill("")
    input_field.type(city_name, delay=80)
    time.sleep(2)

    try:
        option = page.locator(f"p:has-text('{city_name}')").first
        option.wait_for(state="visible", timeout=10000)
        option.click()
        print(f"[OK] Кликнули по '{city_name}' в списке.")
    except Exception:
        print(f"[ERR] Вариант '{city_name}' не найден в списке.")
        return False

    time.sleep(4)

    try:
        header = page.locator("header").first.inner_text()
        if city_name.lower() in header.lower():
            print(f"[OK] Город в шапке: {city_name}")
            return True
        else:
            print(f"[WARN] В шапке не '{city_name}'. Шапка: {header[:150]}")
            return False
    except Exception as e:
        print(f"[WARN] Не удалось прочитать шапку: {e}")
        return False


def ensure_city(page, city_name: str, attempts: int = 3) -> bool:
    """Пытается установить город несколько раз."""
    for i in range(1, attempts + 1):
        print(f"\n[..] Попытка установить город #{i}")
        if select_city(page, city_name):
            return True
        time.sleep(2)
    return False


def parse_card(page) -> dict:
    """Парсит одну карточку события."""
    data = {}
    try:
        # Заголовок: сначала h1, потом og:title
        page.wait_for_selector("h1", timeout=10000)
        title_locator = page.locator("h1").first
        if title_locator.count() > 0:
            data["title"] = title_locator.inner_text().strip()
        else:
            og = page.locator("meta[property='og:title']").first
            data["title"] = og.get_attribute("content") if og.count() > 0 else ""

        main_info = page.locator("div:has-text('Основная информация')").first
        data["main_info"] = main_info.inner_text().strip() if main_info.count() > 0 else ""

        desc = page.locator("div:has-text('Описание')").first
        data["description"] = desc.inner_text().strip() if desc.count() > 0 else ""

        std = page.locator("text='Организация работает по стандарту'").first
        data["standard"] = std.inner_text().strip() if std.count() > 0 else ""

        avail = page.locator("text='Доступно для'").first
        if avail.count() > 0:
            parent = avail.locator("..")
            data["available_for"] = parent.inner_text().strip()
        else:
            data["available_for"] = ""

        social = page.locator("div:has-text('Мероприятие в соцсетях')").first
        if social.count() > 0:
            links = social.locator("a").all()
            data["social_links"] = [
                l.get_attribute("href") for l in links if l.get_attribute("href")
            ]
        else:
            data["social_links"] = []

    except Exception as e:
        print(f"  [ERR] Ошибка парсинга: {e}")
        data["error"] = str(e)

    return data


def is_target_region(card_data: dict, keywords: list) -> bool:
    haystack = (
        (card_data.get("main_info") or "") + " " +
        (card_data.get("title") or "")
    ).lower()
    return any(kw.lower() in haystack for kw in keywords)


def main(region_name: str = "Татарстан", city_title: str = "Казань") -> None:
    """
    Запускает парсер для указанного города.
    Сохраняет результат в dobro_<city_title>.json
    """
    print(f"Регион: {region_name}")
    print(f"Город:  {city_title}\n")

    region_keywords = [region_name, city_title]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="ru-RU",
        )
        page = context.new_page()

        # Шаг 1: главная
        print("Открываем dobro.ru...")
        page.goto("https://dobro.ru", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        # Шаг 2: выбираем город
        if not ensure_city(page, city_title, attempts=3):
            print("\n[ERR] Не удалось установить город. Останавливаемся.")
            page.screenshot(path="debug_city.png")
            browser.close()
            return

        # Шаг 3: страница поиска
        print("\nПереходим на /search...")
        page.goto("https://dobro.ru/search?t=e", wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)

        # Шаг 4: проверяем город
        try:
            header = page.locator("header").first.inner_text()
            if city_title.lower() not in header.lower():
                print("[WARN] После перехода на поиск город сменился.")
                if not ensure_city(page, city_title, attempts=2):
                    print("[ERR] Не удалось. Останавливаемся.")
                    browser.close()
                    return
                page.goto("https://dobro.ru/search?t=e", wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)
            else:
                print(f"[OK] Город '{city_title}' держится.")
        except Exception as e:
            print(f"[WARN] {e}")

        # Шаг 5: собираем ссылки на карточки
        card_links = page.locator("a[href*='/event/']")
        try:
            card_links.first.wait_for(timeout=15000)
        except Exception:
            print("[WARN] Карточки не найдены.")
            page.screenshot(path="debug_search.png")
            browser.close()
            return

        links = card_links.all()
        print(f"Найдено карточек: {len(links)}")

        urls = []
        for link in links:
            href = link.get_attribute("href")
            if href:
                if href.startswith("/"):
                    href = "https://dobro.ru" + href
                urls.append(href)
        urls = list(set(urls))
        print(f"Уникальных ссылок: {len(urls)}\n")

        # Шаг 6: парсим каждую карточку
        results = []
        skipped = 0
        for i, url in enumerate(urls, 1):
            print(f"--- [{i}/{len(urls)}] {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)
                data = parse_card(page)
                data["url"] = url

                if not is_target_region(data, region_keywords):
                    short = (data.get("main_info") or "")[:100].replace("\n", " ")
                    print(f"  [SKIP] Адрес: {short}")
                    skipped += 1
                    continue

                data["region"] = region_name
                data["city"] = city_title
                results.append(data)
                print(f"  [OK] {data['title'][:60]}")
                time.sleep(1)
            except Exception as e:
                print(f"  [ERR] {e}")
                continue

        # Шаг 7: сохраняем JSON
        safe_city = city_title.replace(" ", "_").replace("/", "_")
        output_file = f"dobro_{safe_city}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=4)

        print(f"\n[OK] Готово! Сохранено: {len(results)}, пропущено: {skipped}")
        print(f"     Файл: {output_file}")

        browser.close()


if __name__ == "__main__":
    # Для ручного запуска
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="Татарстан", help="Регион")
    parser.add_argument("--city", default="Казань", help="Город")
    args = parser.parse_args()

    main(region_name=args.region, city_title=args.city)