#!/usr/bin/env python3
"""
Скачивание и подготовка датасета arXiv с Kaggle.

Что делает:
  1. Скачивает архив с Kaggle (если его ещё нет на диске)
  2. Распаковывает (если ещё не распакован)
  3. Читает огромный JSON построчно и складывает в parquet чанками

Каждый шаг проверяет, не сделан ли он уже. Повторный запуск ничего
не перекачивает — просто пропускает готовое.

Запуск:
    python prepare_arxiv.py              # весь датасет (~3-4 млн статей)
    python prepare_arxiv.py --limit 50000   # первые 50 тысяч, для отладки
    python prepare_arxiv.py --peek       # только показать структуру записи

Перед первым запуском:
    pip install kaggle pandas pyarrow
    # положить kaggle.json в ~/.kaggle/ (см. README рядом)
"""

import argparse
import json
import os
import subprocess
import sys
import zipfile
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

DATASET = "Cornell-University/arxiv"
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "01_raw"
OUT_DIR = DATA_DIR / "02_clean"
ZIP_PATH = RAW_DIR / "arxiv.zip"

CHUNK_SIZE = 200_000  # записей на один parquet-файл


# ---------------------------------------------------------------- шаг 1
def step_download():
    """Качает архив с Kaggle. Если файл уже есть — ничего не делает."""
    if list(RAW_DIR.glob("*.json")):
        print("[1/3] json уже распакован на диске, качать нечего")
        return
    if ZIP_PATH.exists():
        size_gb = ZIP_PATH.stat().st_size / 1024**3
        print(f"[1/3] архив уже скачан ({size_gb:.2f} ГБ), пропускаю")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[1/3] качаю {DATASET} с Kaggle — это займёт время...")

    try:
        subprocess.run(
            ["kaggle", "datasets", "download", "-d", DATASET,
             "-p", str(RAW_DIR), "--force"],
            check=True,
        )
    except FileNotFoundError:
        sys.exit(
            "Не найдена команда 'kaggle'.\n"
            "Установи: pip install kaggle\n"
            "И положи kaggle.json в ~/.kaggle/ (инструкция в README)"
        )
    except subprocess.CalledProcessError as e:
        sys.exit(
            f"Kaggle вернул ошибку (код {e.returncode}).\n"
            "Чаще всего это значит: нет файла ~/.kaggle/kaggle.json,\n"
            "или на него не выставлены права 600, или не принято "
            "соглашение об использовании датасета на сайте Kaggle."
        )

    # kaggle кладёт файл как <имя-датасета>.zip — приводим к единому имени
    for f in RAW_DIR.glob("*.zip"):
        if f != ZIP_PATH:
            f.rename(ZIP_PATH)
    print("[1/3] скачано")


# ---------------------------------------------------------------- шаг 2
def step_unzip() -> Path:
    """Распаковывает архив. Возвращает путь к json-файлу внутри."""
    existing = list(RAW_DIR.glob("*.json"))
    if existing:
        print(f"[2/3] уже распаковано: {existing[0].name}, пропускаю")
        return existing[0]

    print("[2/3] распаковываю...")
    with zipfile.ZipFile(ZIP_PATH) as z:
        names = z.namelist()
        print("      внутри архива:", names)
        z.extractall(RAW_DIR)

    json_files = list(RAW_DIR.glob("*.json"))
    if not json_files:
        sys.exit(f"В архиве не нашлось .json файла. Содержимое: {names}")

    size_gb = json_files[0].stat().st_size / 1024**3
    print(f"[2/3] распаковано: {json_files[0].name} ({size_gb:.2f} ГБ)")
    return json_files[0]


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

    Внимание: в этом датасете даты лежат в формате писем
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


# ---------------------------------------------------------------- шаг 3
def step_convert(json_path: Path, limit: int | None):
    """Читает json построчно и пишет parquet чанками."""
    suffix = f"_limit{limit}" if limit else ""
    out_dir = OUT_DIR if not limit else Path(f"{OUT_DIR}{suffix}")

    if out_dir.exists() and any(out_dir.glob("*.parquet")):
        print(f"[3/3] parquet уже собран в {out_dir}, пропускаю")
        return out_dir

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[3/3] конвертирую в parquet → {out_dir}")

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
    print(f"[3/3] готово: {total:,} записей, битых строк пропущено: {skipped}")
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
    args = ap.parse_args()

    step_download()
    json_path = step_unzip()

    if args.peek:
        peek(json_path)
        return

    out_dir = step_convert(json_path, args.limit)
    summary(out_dir)


if __name__ == "__main__":
    main()