"""AWS S3 storage service for file uploads and downloads."""

import logging
import boto3
from botocore.exceptions import ClientError
from typing import Optional, BinaryIO
import uuid

from app.config import settings
from app.utils.exceptions import StorageError

logger = logging.getLogger(__name__)


class S3Service:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if not self._client:
            if not settings.AWS_ACCESS_KEY_ID:
                raise StorageError("AWS credentials not configured")
            self._client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
        return self._client

    async def upload_file(
        self,
        file_content: bytes,
        key: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> str:
        """Upload file to S3 and return the URL."""
        try:
            client = self._get_client()
            client.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=key,
                Body=file_content,
                ContentType=content_type,
                Metadata=metadata or {},
            )
            url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
            logger.info(f"Uploaded file to S3: {key}")
            return url
        except ClientError as e:
            raise StorageError(f"S3 upload failed: {e}")

    async def download_file(self, key: str) -> bytes:
        """Download file from S3."""
        try:
            client = self._get_client()
            response = client.get_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
            return response["Body"].read()
        except ClientError as e:
            raise StorageError(f"S3 download failed: {e}")

    async def delete_file(self, key: str) -> None:
        """Delete file from S3."""
        try:
            client = self._get_client()
            client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
        except ClientError as e:
            raise StorageError(f"S3 delete failed: {e}")

    def generate_key(self, prefix: str, filename: str) -> str:
        """Generate a unique S3 key."""
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        return f"{prefix}/{uuid.uuid4().hex}.{ext}"

    async def get_presigned_url(self, key: str, expiry: int = 3600) -> str:
        """Generate a pre-signed URL for temporary access."""
        try:
            client = self._get_client()
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
                ExpiresIn=expiry,
            )
            return url
        except ClientError as e:
            raise StorageError(f"Pre-signed URL generation failed: {e}")


s3_service = S3Service()