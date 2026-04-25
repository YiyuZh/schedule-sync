from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

SENSITIVE_KEYS = {"ai_api_key", "api_key", "secret_key"}


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitize_payload(item)
            for key, item in value.items()
            if str(key).lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    return value


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


def content_hash(value: Any) -> str:
    return sha256(dumps_json(value).encode("utf-8")).hexdigest()
