from __future__ import annotations

import uuid
from urllib.parse import urlparse, urlunparse

import boto3
from botocore.client import BaseClient

from app.core.config import settings


def _client() -> BaseClient:
    if not settings.s3_endpoint_url:
        raise RuntimeError("S3 não configurado (S3_ENDPOINT_URL)")
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )


def ensure_bucket_exists() -> None:
    if not settings.s3_endpoint_url:
        return
    c = _client()
    b = settings.s3_bucket
    try:
        c.head_bucket(Bucket=b)
    except Exception:
        c.create_bucket(Bucket=b)


def upload_fileobj(fileobj, key: str, content_type: str | None) -> None:
    extra: dict = {}
    if content_type:
        extra["ContentType"] = content_type
    kwargs = {}
    if extra:
        kwargs["ExtraArgs"] = extra
    _client().upload_fileobj(fileobj, settings.s3_bucket, key, **kwargs)


def build_attachment_key(project_id: int, original_name: str) -> str:
    safe = "".join(c for c in original_name if c.isalnum() or c in "._- ")[:180] or "file"
    return f"projects/{project_id}/{uuid.uuid4().hex}_{safe}"


def delete_object_key(key: str) -> None:
    """Remove objeto do bucket S3/MinIO (ignora erros)."""
    if not settings.s3_endpoint_url or not key or key.startswith("local_storage"):
        return
    try:
        _client().delete_object(Bucket=settings.s3_bucket, Key=key)
    except Exception:
        pass


def list_object_keys_under_prefix(prefix: str) -> list[str]:
    """Lista chaves de objectos (ficheiros) com o prefixo dado."""
    if not settings.s3_endpoint_url:
        raise RuntimeError("S3 não configurado (S3_ENDPOINT_URL)")
    c = _client()
    b = settings.s3_bucket
    p = prefix.rstrip("/") + "/"
    out: list[str] = []
    paginator = c.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=b, Prefix=p):
        for obj in page.get("Contents", []):
            k = obj.get("Key")
            if k and not str(k).endswith("/"):
                out.append(str(k))
    return out


def relative_paths_under_prefix(prefix: str, keys: list[str]) -> list[str]:
    base = prefix.rstrip("/") + "/"
    rel = []
    for k in keys:
        if k.startswith(base):
            rel.append(k[len(base) :])
    return sorted(rel)


def read_object_bytes(key: str) -> bytes:
    if not settings.s3_endpoint_url:
        raise RuntimeError("S3 não configurado (S3_ENDPOINT_URL)")
    c = _client()
    r = c.get_object(Bucket=settings.s3_bucket, Key=key)
    return r["Body"].read()


def content_type_for_storage_key(key: str) -> str:
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    if ext == "json":
        return "application/json"
    if ext in ("html", "htm"):
        return "text/html; charset=utf-8"
    if ext == "svg":
        return "image/svg+xml"
    if ext == "png":
        return "image/png"
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    if ext == "webp":
        return "image/webp"
    if ext == "txt":
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def presigned_get_url(key: str) -> str:
    url = _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=settings.s3_presigned_ttl_seconds,
    )
    if settings.s3_public_endpoint_url and settings.s3_endpoint_url:
        pub = urlparse(settings.s3_public_endpoint_url)
        u = urlparse(url)
        url = urlunparse(
            (
                pub.scheme or u.scheme,
                pub.netloc or u.netloc,
                u.path,
                u.params,
                u.query,
                u.fragment,
            )
        )
    return url
