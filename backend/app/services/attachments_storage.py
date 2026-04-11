from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.services.storage import build_attachment_key, delete_object_key, upload_fileobj


def remove_attachment_storage(storage_path: str) -> None:
    """Apaga ficheiro local ou chave S3 associada ao anexo (best-effort)."""
    if not storage_path:
        return
    path = Path(storage_path)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
        return
    delete_object_key(storage_path)


async def save_upload(project_id: int, upload: UploadFile) -> tuple[str, int, str | None]:
    data = await upload.read()
    size = len(data)
    ctype = upload.content_type
    name = upload.filename or "arquivo"
    if settings.s3_endpoint_url:
        key = build_attachment_key(project_id, name)
        upload_fileobj(BytesIO(data), key, ctype)
        return key, size, ctype
    base = Path("local_storage") / str(project_id)
    base.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}_{name}"
    path = base / fname
    path.write_bytes(data)
    return str(path.as_posix()), size, ctype
