"""User-approved local knowledge store; AI output is never trusted by default."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from recorder import app_data_dir


def _path() -> Path:
    directory = app_data_dir() / "knowledge"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "references.json"


def list_references() -> list[dict[str, Any]]:
    path = _path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    refs = payload.get("references", []) if isinstance(payload, dict) else []
    if not isinstance(refs, list):
        return []
    return [item for item in refs if isinstance(item, dict) and item.get("user_approved") is True]


def save_reference(title: str, source: str, notes: str) -> dict[str, Any]:
    """Persist analysis only after explicit user approval."""
    notes = (notes or "").strip()
    if not notes:
        raise ValueError("Cannot save empty notes.")
    path = _path()
    record = {
        "title": (title or "Reviewed reference").strip()[:120],
        "source": (source or "user review").strip()[:40],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "user_approved": True,
        "notes": notes[:12000],
    }
    records = (list_references() + [record])[-80:]
    payload = json.dumps({"version": 1, "references": records}, ensure_ascii=False, indent=2)
    fd, temp_name = tempfile.mkstemp(prefix="references-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return record


def load_reference_context(max_items: int = 5, max_chars: int = 3600) -> str:
    blocks = []
    for item in reversed(list_references()[-max(1, max_items):]):
        notes = str(item.get("notes", "")).strip()
        if notes:
            title = str(item.get("title", "Reference"))[:120]
            source = str(item.get("source", "unknown"))[:40]
            blocks.append(f"[{title} | source: {source}]\n{notes}")
    return "\n\n".join(blocks)[:max(0, max_chars)]
