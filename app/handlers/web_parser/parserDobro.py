import httpx
from playwright.sync_api import sync_playwright


class ParserDobro:
    def __init__(self, link: str) -> None:
        self.link = link
        self.status = None

    def check_status_httpx(self) -> int:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        try:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=10.0) as client:
                print(f"[httpx] Отправляем запрос на {self.link}...")
                response = client.get(self.link)
                status = response.status_code
                print(f"[httpx] Статус код: {status}")
                print(f"[httpx] Финальный URL: {response.url}")
                if status == 200:
                    print("[httpx] Сайт доступен!")
                else:
                    print(f"[httpx] Сайт вернул код {status}")
                self.status = status
                return status
        except httpx.RequestError as e:
            print(f"[httpx] Ошибка: {e}")
            self.status = None
            return None

    def check_status_playwright(self) -> int:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="ru-RU"
            )
            page = context.new_page()
            try:
                print(f"[playwright] Переходим на {self.link}...")
                response = page.goto(self.link, wait_until="domcontentloaded", timeout=30000)
                status = response.status if response else None
                print(f"[playwright] Статус код: {status}")
                print(f"[playwright] Заголовок: {page.title()}")
                if status == 200:
                    print("[playwright] Сайт доступен!")
                    page.screenshot(path="dobro_status.png")
                    print("[playwright] Скриншот сохранён.")
                else:
                    print(f"[playwright] Код {status}")
                self.status = status
                return status
            except Exception as e:
                print(f"[playwright] Ошибка: {e}")
                self.status = None
                return None
            finally:
                browser.close()

    def get_status(self) -> int:
        print("--- Попытка 1: httpx ---")
        status_httpx = self.check_status_httpx()
        if status_httpx == 200:
            return 200
        print("\n--- Попытка 2: playwright ---")
        status_playwright = self.check_status_playwright()
        return status_playwright

    def print_status(self) -> None:
        print(f"\nИтоговый статус: {self.status}")


if __name__ == "__main__":
    parser = ParserDobro("https://dobro.ru")
    parser.get_status()
    parser.print_status()
