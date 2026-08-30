"""S3-compatible object storage client with automatic local file fallback."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import BinaryIO

from backend.config import get_settings

try:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import BotoCoreError, ClientError

    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


class ObjectStorage:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.bucket = self.settings.s3_bucket
        self.local_storage_dir = Path("data/storage")
        self.local_storage_dir.mkdir(parents=True, exist_ok=True)
        self._s3_client = None
        self._use_local = False

        if HAS_BOTO3 and self.settings.s3_endpoint:
            try:
                self._s3_client = boto3.client(
                    "s3",
                    endpoint_url=self.settings.s3_endpoint,
                    aws_access_key_id=self.settings.s3_access_key,
                    aws_secret_access_key=self.settings.s3_secret_key,
                    region_name=self.settings.s3_region,
                    config=Config(signature_version="s3v4", connect_timeout=1, read_timeout=2),
                )
            except Exception:
                self._use_local = True
        else:
            self._use_local = True

    def ensure_bucket(self) -> None:
        if self._use_local or not self._s3_client:
            return
        try:
            self._s3_client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self._s3_client.create_bucket(Bucket=self.bucket)
            except Exception:
                self._use_local = True

    def upload(self, key: str, data: bytes | BinaryIO, content_type: str) -> str:
        body = data if isinstance(data, bytes) else data.read()
        if not self._use_local and self._s3_client:
            try:
                self.ensure_bucket()
                self._s3_client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)
                return key
            except Exception:
                self._use_local = True

        # Local fallback
        dest_path = self.local_storage_dir / key
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(body)
        return key

    def download(self, key: str) -> bytes:
        if not self._use_local and self._s3_client:
            try:
                response = self._s3_client.get_object(Bucket=self.bucket, Key=key)
                return response["Body"].read()
            except Exception:
                pass

        dest_path = self.local_storage_dir / key
        if dest_path.exists():
            return dest_path.read_bytes()
        raise FileNotFoundError(f"Storage key not found: {key}")

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        if not self._use_local and self._s3_client:
            try:
                return self._s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=expires_in,
                )
            except Exception:
                pass
        return f"/api/v1/storage/{key}"

    def upload_bytes(self, key: str, data: bytes, content_type: str) -> str:
        return self.upload(key, io.BytesIO(data), content_type)
