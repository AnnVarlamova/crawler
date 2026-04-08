from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.config import CACHE_DIR, CACHE_VERSION
from app.utils import ensure_dir

T = TypeVar("T", bound=BaseModel)


def _cache_path(kind: str, payload: object) -> Path:
    raw = json.dumps(
        {
            "version": CACHE_VERSION,
            "kind": kind,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return CACHE_DIR / kind / f"{digest}.json"


def load_cached_model(kind: str, payload: object, model_cls: type[T]) -> T | None:
    path = _cache_path(kind, payload)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return model_cls.model_validate(data)
    except Exception:
        return None


def save_cached_model(kind: str, payload: object, model: BaseModel) -> None:
    path = _cache_path(kind, payload)
    ensure_dir(path.parent)
    path.write_text(
        json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )