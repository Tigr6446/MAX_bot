# MAX Event Bot

Бот-агрегатор событий для мессенджера MAX. Парсит сообщения из каналов (спорт, волонтёрство, досуг), фильтрует их через языковую модель и отправляет пользователю только релевантные события по его интересам.

**Бот в MAX:** [@t277_hakaton_max_bot](https://max.ru/t277_hakaton_max_bot)

## Стек

- Python 3.12
- [maxapi](https://pypi.org/project/maxapi/) — библиотека для работы с MAX Bot API
- FastAPI + Uvicorn — веб-сервер для приёма вебхуков
- PostgreSQL 16 — хранение пользователей и событий
- SQLAlchemy (async) + asyncpg — ORM и драйвер БД
- Docker + Docker Compose — контейнеризация

