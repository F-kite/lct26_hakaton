"""Создать новые таблицы (signals, signal_sources, search_queries) и
добавить колонки, появившиеся в уже существующих таблицах после первого
запуска.

sources/feed_items уже существуют (создаёт collector) — create_all их не
трогает: по умолчанию проверяет наличие таблицы в БД и пропускает, если
она уже есть. Та же логика верна и для наших таблиц: create_all не делает
ALTER TABLE для новых колонок на уже существующей таблице (у нас нет
Alembic/миграций) — поэтому недостающие колонки добавляются здесь вручную,
идемпотентно (IF NOT EXISTS), при каждом старте контейнера.
"""

from sqlalchemy import text

from .db import Base, engine

# (таблица, колонка, тип) — то, что появилось после первого create_all
_EXTRA_COLUMNS = [
    ("signals", "potential_advantage", "TEXT"),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, column, coltype in _EXTRA_COLUMNS:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}"))


if __name__ == "__main__":
    init_db()
    print("Таблицы созданы.")
