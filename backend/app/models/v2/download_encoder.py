"""Скачать энкодер E5 для модели v2 и сверить sha256."""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

REPO = "intfloat/multilingual-e5-small"
REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"

FILES = {
    "config.json": ("config.json", "69137736cab8b8903a07fe8afaafdda25aac55415a12a55d1bffa9f581abf959"),
    "special_tokens_map.json": ("special_tokens_map.json", "d05497f1da52c5e09554c0cd874037a083e1dc1b9cfd48034d1c717f1afc07a7"),
    "tokenizer.json": ("tokenizer.json", "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"),
    "tokenizer_config.json": ("tokenizer_config.json", "a1d6bc8734a6f635dc158508bef000f8e2e5a759c7d92f984b2c86e5ff53425b"),
    "onnx/model_qint8_avx512_vnni.onnx": (
        "onnx/model_qint8_avx512_vnni.onnx",
        "dd476dd0c2514e9b9be83aeb3853fac0763e0bdf4a71645407587d77c48a2d88",
    ),
}

DEFAULT_DIR = Path(__file__).resolve().parent / "encoder"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(target: Path = DEFAULT_DIR) -> None:
    for remote, (local, expected) in FILES.items():
        dest = target / local
        if dest.exists() and _sha256(dest) == expected:
            print(f"ok (уже есть) {local}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{remote}"
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        actual = _sha256(tmp)
        if actual != expected:
            tmp.unlink()
            raise SystemExit(f"sha256 не совпал для {remote}: {actual} != {expected}")
        tmp.replace(dest)
        print(f"ok {local}")


if __name__ == "__main__":
    download(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR)
