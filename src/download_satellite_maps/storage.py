"""Minimal Hugging Face Xet-bucket I/O for canopyboard-storage.

Mirrors the pattern in download-process-als/storage/hf.py: writes go through
`sync_bucket` (staged in a temp dir so only the intended object is pushed)."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

from .config import HF_BUCKET


def list_bucket(prefix: str, recursive: bool = False):
    try:
        return list(HfApi().list_bucket_tree(HF_BUCKET, prefix, recursive=recursive))
    except Exception:
        return []


def exists(key: str) -> bool:
    parent = str(Path(key).parent)
    parent = "" if parent == "." else parent
    return any(getattr(e, "path", None) == key for e in list_bucket(parent))


def upload_file(local_path: str | Path, dest_prefix: str) -> str:
    """Upload one file to `<dest_prefix>/<name>` in the bucket; return the key."""
    local_path = Path(local_path)
    dest_prefix = dest_prefix.rstrip("/")
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(local_path, Path(tmp) / local_path.name)
        HfApi().sync_bucket(
            source=tmp, dest=f"hf://buckets/{HF_BUCKET}/{dest_prefix}/",
        )
    return f"{dest_prefix}/{local_path.name}"


def download_one(key: str, dest_dir: str | Path) -> str:
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    local = str(Path(dest_dir) / Path(key).name)
    HfApi().download_bucket_files(
        bucket_id=HF_BUCKET, files=[(key, local)], raise_on_missing_files=True,
    )
    return local
