"""
Одноразовый скрипт: тянет последние посты из канала и печатает
все LINK-элементы с их атрибутами.
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    # Замени на реальные chat_id из .env (PARSER_CHANNELS)
    channels = [-68690638487622]  # <-- сюда свои chat_id

    flow = QrAuthFlow(ConsoleQrHandler())
    client = WebClient(
        auth_flow=flow,
        work_dir="cache",
        session_name="web.db",
        extra_config=ExtraConfig(sync=SyncOverrides(chats_sync=-1)),
    )

    start_task = asyncio.create_task(client.start())
    await asyncio.sleep(5)

    for chat_id in channels:
        print(f"\n{'='*60}\nКАНАЛ {chat_id}\n{'='*60}")
        try:
            history = await client.fetch_history(chat_id=chat_id, backward=5)
        except Exception as e:
            print(f"Ошибка: {e}")
            continue

        for msg in history:
            text = getattr(msg, "text", None) or ""
            elements = getattr(msg, "elements", None) or []

            link_els = [el for el in elements if getattr(el, "type", None) == "LINK"]
            if not link_els:
                continue

            print(f"\n--- msg id={getattr(msg, 'id', '?')} ---")
            print(f"TEXT: {text[:200]}...")
            for el in link_els:
                attrs = getattr(el, "attributes", None)
                print(f"  LINK el: type={type(el).__name__}")
                print(f"    from   = {getattr(el, 'from', None)}")
                print(f"    length = {getattr(el, 'length', None)}")
                print(f"    attrs  = {vars(attrs) if hasattr(attrs, '__dict__') else attrs}")

                # Проверим, что реально лежит по этим позициям в тексте
                f = getattr(el, "from", None)
                l = getattr(el, "length", None)
                if f is not None and l is not None:
                    print(f"    anchor = '{text[f:f+l]}'")
                    print(f"    url_in_text = {attrs.url in text if attrs else '?'}")

    await client.stop()
    start_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())