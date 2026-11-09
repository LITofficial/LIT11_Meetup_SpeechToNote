"""Explicitly prepared local models; importing this module never downloads."""
import hashlib
import json
from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parents[2] / "models"
CATALOG = {"base": "Base", "small": "Small", "large-v3-turbo": "Turbo"}
REPOSITORIES = {"base": "Systran/faster-whisper-base", "small": "Systran/faster-whisper-small", "large-v3-turbo": "dropbox-dash/faster-whisper-large-v3-turbo"}
REQUIRED = ("model.bin", "config.json", "tokenizer.json")


def model_path(model_id, root=MODEL_ROOT):
    if model_id not in CATALOG:
        raise ValueError("INVALID_MODEL")
    return Path(root) / model_id


def ready(model_id, root=MODEL_ROOT):
    path = model_path(model_id, root)
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        return all((path / name).is_file() and (path / name).stat().st_size == manifest["files"][name]["bytes"] for name in REQUIRED)
    except (OSError, KeyError, ValueError):
        return False


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
