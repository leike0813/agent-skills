from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
from pathlib import Path
from typing import Any

from . import deterministic_core


def _temp_payload(payload: dict[str, Any]) -> Path:
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
    with tmp:
        json.dump(payload, tmp, ensure_ascii=False)
    return Path(tmp.name)


def call_algorithm_handler(
    handler_name: str,
    db_path: Path,
    *,
    payload: dict[str, Any] | None = None,
    **extra: Any,
) -> tuple[dict[str, Any], int]:
    handler = getattr(deterministic_core, handler_name)
    temp_path: Path | None = None
    payload_file = ""
    if payload is not None:
        temp_path = _temp_payload(payload)
        payload_file = str(temp_path)
    namespace_values = {
        "db_path": str(db_path.resolve()),
        "payload_file": payload_file,
        "out_path": "",
        "persist_db_only": False,
        "mode": "",
        "source_path": "",
        "preprocess_artifact": "",
        "in_path": "",
        "out_dir": "",
        **extra,
    }
    args = argparse.Namespace(**namespace_values)
    stream = io.StringIO()
    try:
        with contextlib.redirect_stdout(stream):
            code = handler(args)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    stdout = stream.getvalue().strip()
    try:
        result = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        result = {"error": {"code": "algorithm_handler_invalid_json", "message": stdout or "algorithm handler produced no JSON"}}
        code = 1
    return result, int(code)
