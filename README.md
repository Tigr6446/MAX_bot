# MAX Event Bot

Бот-агрегатор событий для мессенджера MAX. Парсит сообщения из каналов (спорт, волонтёрство, досуг), фильтрует их через эвристику и отправляет пользователю только релевантные события по его интересам.

**Бот в MAX:** [@t277_hakaton_max_bot](https://max.ru/t277_hakaton_max_bot)

# Пользовательский сценарий:


# Стек

- Python 3.12
- [maxapi](https://pypi.org/project/maxapi/) — библиотека для работы с MAX Bot API
- FastAPI + Uvicorn — веб-сервер для приёма вебхуков
- PostgreSQL 16 — хранение пользователей и событий
- SQLAlchemy (async) + asyncpg — ORM и драйвер БД
- Docker + Docker Compose — контейнеризация

# Состав и архитектура решения
- `main.py` — точка входа, FastAPI + вебхук MAX.
- `app/handlers/` — обработчики команд и онбординга.
- `app/handlers/channels/` — парсер каналов MAX.
- `app/handlers/user_command_scripts/` — команды пользователя, настройки.
- `app/Analyzer/` — эвристический анализатор текста.
- `app/background/` — фоновые задачи (парсер, библиотекарь).
- `app/database/` — модели и запросы к PostgreSQL.
- `app/config.py` — настройки через `.env`.

