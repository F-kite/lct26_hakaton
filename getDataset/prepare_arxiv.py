#!/usr/bin/env python3
"""
Скачивание и подготовка датасета arXiv с Kaggle.

Что делает:
  1. Скачивает датасет через kagglehub (архив распаковывается сам)
  2. Читает огромный JSON построчно и складывает в parquet чанками

Каждый шаг проверяет, не сделан ли он уже. Повторный запуск ничего
не перекачивает — просто пропускает готовое.

Запуск:
    python prepare_arxiv.py                 # весь датасет
    python prepare_arxiv.py --limit 50000   # первые 50 тысяч, для отладки
    python prepare_arxiv.py --peek          # только показать структуру записи
    python prepare_arxiv.py --login         # ввести токен Kaggle интерактивно

Перед первым запуском:
    pip install kagglehub pandas pyarrow
"""

import argparse
import json
import sys
import zipfile
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

DATASET = "Cornell-University/arxiv"
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "01_raw"
OUT_DIR = DATA_DIR / "02_clean"

CHUNK_SIZE = 200_000  # записей на один parquet-файл


# ---------------------------------------------------------------- шаг 1
def step_download() -> Path:
    """
    Качает датасет через kagglehub и возвращает путь к json-файлу.

    output_dir заставляет класть файлы прямо в проект, а не в кеш
    ~/.cache/kagglehub — иначе пять гигабайт улетят в домашний раздел,
    и ты их потом не найдёшь.
    """
    existing = sorted(RAW_DIR.rglob("*.json"))
    if existing:
        size_gb = existing[0].stat().st_size / 1024**3
        print(f"[1/2] уже скачано: {existing[0].name} ({size_gb:.2f} ГБ), пропускаю")
        return existing[0]

    try:
        import kagglehub
    except ImportError:
        sys.exit("Нет библиотеки kagglehub. Установи: pip install kagglehub")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[1/2] качаю {DATASET} — это надолго, файл около 1,5 ГБ в архиве")

    try:
        path = Path(kagglehub.dataset_download(DATASET, output_dir=str(RAW_DIR)))
    except Exception as e:
        sys.exit(
            f"kagglehub не смог скачать датасет:\n  {type(e).__name__}: {e}\n\n"
            "Частые причины:\n"
            "  - не заданы доступы. Запусти: python prepare_arxiv.py --login\n"
            "  - не принято соглашение: открой страницу датасета в браузере\n"
            f"    https://www.kaggle.com/datasets/{DATASET} и нажми Download\n"
            "  - кончилось место на диске (нужно около 12 ГБ суммарно)"
        )

    print(f"[1/2] скачано в {path}")

    # kagglehub обычно распаковывает архив сам, но подстрахуемся
    json_files = sorted(RAW_DIR.rglob("*.json"))
    if not json_files:
        zips = sorted(RAW_DIR.rglob("*.zip"))
        if not zips:
            sys.exit(f"В {RAW_DIR} нет ни .json, ни .zip. Что скачалось: "
                     f"{[p.name for p in RAW_DIR.rglob('*')][:20]}")
        print(f"      архив не распакован автоматически, распаковываю {zips[0].name}")
        with zipfile.ZipFile(zips[0]) as z:
            z.extractall(RAW_DIR)
        json_files = sorted(RAW_DIR.rglob("*.json"))
        if not json_files:
            sys.exit("В архиве не нашлось .json файла")

    size_gb = json_files[0].stat().st_size / 1024**3
    print(f"[1/2] готово: {json_files[0].name} ({size_gb:.2f} ГБ)")
    return json_files[0]


def do_login():
    """Интерактивный ввод токена Kaggle. Сохраняется глобально."""
    import kagglehub
    kagglehub.login()
    print("Доступы сохранены. Теперь запусти скрипт обычным способом.")


# ---------------------------------------------------------------- утилиты
def peek(json_path: Path, n: int = 2):
    """Показывает, как реально устроена одна запись. Ничего не меняет."""
    print(f"\n--- первые {n} записей из {json_path.name} ---")
    with open(json_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            rec = json.loads(line)
            if i == 0:
                print("ПОЛЯ:", list(rec.keys()), "\n")
            print(json.dumps(rec, ensure_ascii=False, indent=2)[:1500])
            print("...\n")


def first_version_date(rec: dict):
    """
    Дата первой публикации препринта.

    Внимание: в этом датасете даты лежат в почтовом формате
    ('Mon, 2 Apr 2007 19:18:42 GMT'), а не ISO. Обычный
    pd.to_datetime на них спотыкается — парсим правильным парсером.
    """
    versions = rec.get("versions") or []
    if not versions:
        return None
    try:
        return parsedate_to_datetime(versions[0]["created"])
    except (KeyError, TypeError, ValueError):
        return None


def to_row(rec: dict) -> dict:
    """Оставляем только то, что нужно для анализа трендов."""
    dt = first_version_date(rec)
    cats = (rec.get("categories") or "").split()
    return {
        "id": rec.get("id"),
        "title": (rec.get("title") or "").replace("\n", " ").strip(),
        "abstract": (rec.get("abstract") or "").replace("\n", " ").strip(),
        "categories": cats,
        "primary_category": cats[0] if cats else None,
        "created": dt,
        "year": dt.year if dt else None,
        "quarter": f"{dt.year}Q{(dt.month - 1) // 3 + 1}" if dt else None,
        "n_authors": len(rec.get("authors_parsed") or []),
        "doi": rec.get("doi"),
        "journal_ref": rec.get("journal-ref"),
        "n_versions": len(rec.get("versions") or []),
    }


# ---------------------------------------------------------------- шаг 2
def step_convert(json_path: Path, limit: int | None) -> Path:
    """Читает json построчно и пишет parquet чанками."""
    out_dir = OUT_DIR if not limit else Path(f"{OUT_DIR}_limit{limit}")

    if out_dir.exists() and any(out_dir.glob("*.parquet")):
        print(f"[2/2] parquet уже собран в {out_dir}, пропускаю")
        return out_dir

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[2/2] конвертирую в parquet → {out_dir}")

    buffer, chunk_no, total, skipped = [], 0, 0, 0

    def flush():
        nonlocal buffer, chunk_no
        if not buffer:
            return
        df = pd.DataFrame(buffer)
        path = out_dir / f"part_{chunk_no:04d}.parquet"
        df.to_parquet(path, index=False)
        print(f"      {path.name}: {len(df):,} записей")
        buffer, chunk_no = [], chunk_no + 1

    with open(json_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            buffer.append(to_row(rec))
            total += 1

            if len(buffer) >= CHUNK_SIZE:
                flush()
            if limit and total >= limit:
                break

    flush()
    print(f"[2/2] готово: {total:,} записей, битых строк пропущено: {skipped}")
    return out_dir


def summary(out_dir: Path):
    """Короткая сводка — проверка, что данные живые."""
    df = pd.read_parquet(out_dir, columns=["year", "primary_category"])
    print("\n--- сводка ---")
    print(f"всего записей: {len(df):,}")
    years = df["year"].dropna()
    if len(years):
        print(f"годы: {int(years.min())} — {int(years.max())}")
        print("\nстатей по годам (последние 8):")
        print(years.astype(int).value_counts().sort_index().tail(8).to_string())
    print("\nтоп-10 категорий:")
    print(df["primary_category"].value_counts().head(10).to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="обработать только первые N записей")
    ap.add_argument("--peek", action="store_true",
                    help="только показать структуру записи и выйти")
    ap.add_argument("--login", action="store_true",
                    help="ввести токен Kaggle интерактивно и выйти")
    args = ap.parse_args()

    if args.login:
        do_login()
        return

    json_path = step_download()

    if args.peek:
        peek(json_path)
        return

    out_dir = step_convert(json_path, args.limit)
    summary(out_dir)


if __name__ == "__main__":
    main()
