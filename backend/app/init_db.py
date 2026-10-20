"""Создаёт новые таблицы и добавляет колонки, которых не было при первом
запуске — create_all не делает ALTER TABLE на существующих таблицах (нет
Alembic), поэтому недостающие колонки добавляются здесь вручную, идемпотентно.
"""

from sqlalchemy import text

from .db import Base, engine

# (таблица, колонка, тип) — то, что появилось после первого create_all
_EXTRA_COLUMNS = [
    ("signals", "potential_advantage", "TEXT"),
    ("signals", "problem", "TEXT"),
    ("signals", "status", "VARCHAR(16) DEFAULT 'included'"),
    ("search_queries", "phase", "VARCHAR(32)"),
    ("search_queries", "date_from", "DATE"),
    ("search_queries", "date_to", "DATE"),
    ("signal_sources", "is_primary", "BOOLEAN DEFAULT FALSE"),
    ("signal_sources", "relation", "VARCHAR(16)"),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, column, coltype in _EXTRA_COLUMNS:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}"))


if __name__ == "__main__":
    init_db()
    print("Таблицы созданы.")
