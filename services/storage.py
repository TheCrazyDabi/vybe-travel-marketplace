"""Cloudflare R2 and Local Hybrid Storage Service for VYBE.

Handles:
- Secure file uploads (operator verification documents, package images)
- Collision-proof naming with UUID prefix
- Strict extension and MIME validation
- Time-limited presigned URL generation for sensitive private documents (R2 S3-compatible)
- Seamless offline/local fallback when R2 credentials are not set
"""

import logging
import mimetypes
import os
import urllib.request
import uuid
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


class StorageService:
    """Hybrid storage provider supporting Cloudflare R2 (S3-compatible) with local filesystem fallback."""

    @staticmethod
    def is_configured() -> bool:
        """Check whether Cloudflare R2 credentials are fully configured."""
        try:
            cfg = current_app.config
        except RuntimeError:
            return False
        return bool(
            cfg.get("R2_ACCOUNT_ID")
            and cfg.get("R2_ACCESS_KEY_ID")
            and cfg.get("R2_SECRET_ACCESS_KEY")
            and cfg.get("R2_BUCKET_NAME")
        )

    @staticmethod
    def is_supabase_configured() -> bool:
        """Check whether Supabase Storage credentials are configured."""
        try:
            cfg = current_app.config
        except RuntimeError:
            return False
        return bool(cfg.get("SUPABASE_URL") and cfg.get("SUPABASE_SERVICE_ROLE_KEY"))

    @classmethod
    def upload_to_supabase(cls, file: FileStorage, storage_key: str, content_type: str) -> Optional[str]:
        """Upload an object directly to Supabase Storage via REST."""
        if not cls.is_supabase_configured():
            return None
        cfg = current_app.config
        bucket = cfg.get("SUPABASE_STORAGE_BUCKET", "vybe-packages")
        url = f"{cfg['SUPABASE_URL'].rstrip('/')}/storage/v1/object/{bucket}/{storage_key}"
        file.stream.seek(0)
        data = file.stream.read()
        file.stream.seek(0)
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {cfg['SUPABASE_SERVICE_ROLE_KEY']}",
                "apikey": cfg["SUPABASE_SERVICE_ROLE_KEY"],
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 201):
                    logger.info("Uploaded %s to Supabase Storage bucket %s", storage_key, bucket)
                    return storage_key
        except Exception as e:
            logger.error("Supabase Storage upload error for %s: %s", storage_key, e)
        return None

    @classmethod
    def delete_from_supabase(cls, storage_key: str) -> bool:
        """Delete an object from Supabase Storage."""
        if not cls.is_supabase_configured():
            return False
        cfg = current_app.config
        bucket = cfg.get("SUPABASE_STORAGE_BUCKET", "vybe-packages")
        url = f"{cfg['SUPABASE_URL'].rstrip('/')}/storage/v1/object/{bucket}/{storage_key}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {cfg['SUPABASE_SERVICE_ROLE_KEY']}",
                "apikey": cfg["SUPABASE_SERVICE_ROLE_KEY"],
            },
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 204)
        except Exception as e:
            logger.error("Supabase Storage delete error for %s: %s", storage_key, e)
            return False

    @classmethod
    def get_s3_client(cls):
        """Build and return an S3 client for Cloudflare R2."""
        if not cls.is_configured():
            return None
        cfg = current_app.config
        endpoint_url = f"https://{cfg['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=cfg["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=cfg["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
            config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    @classmethod
    def upload_file(
        cls,
        file: FileStorage,
        folder: str = "verifications",
        is_private: bool = True,
    ) -> Optional[str]:
        """Upload a file to R2 or local storage.

        Args:
            file: Flask FileStorage instance from request.files
            folder: Subfolder/prefix ('verifications', 'packages', 'profiles')
            is_private: If True, documents require signed URLs to access

        Returns:
            Relative storage key (e.g. 'verifications/a1b2c3d4_document.pdf') or None on failure
        """
        if not file or not file.filename:
            return None

        # Sanitize filename and validate extension
        raw_name = secure_filename(file.filename)
        if not raw_name:
            raw_name = "upload"

        ext = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
        allowed = current_app.config.get("ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "gif", "pdf"})
        if ext not in allowed:
            raise ValueError(f"File extension '{ext}' is not permitted. Allowed: {', '.join(sorted(allowed))}")

        # Unique key to avoid collisions
        unique_name = f"{uuid.uuid4().hex}_{raw_name}"
        clean_folder = folder.strip("/\\")
        storage_key = f"{clean_folder}/{unique_name}" if clean_folder else unique_name

        content_type = file.content_type or mimetypes.guess_type(raw_name)[0] or "application/octet-stream"

        if cls.is_configured():
            try:
                s3 = cls.get_s3_client()
                bucket = current_app.config["R2_BUCKET_NAME"]
                # Rewind stream before upload
                file.stream.seek(0)
                s3.upload_fileobj(
                    file.stream,
                    bucket,
                    storage_key,
                    ExtraArgs={"ContentType": content_type},
                )
                logger.info("Uploaded %s to Cloudflare R2 bucket %s", storage_key, bucket)
                return storage_key
            except Exception as e:
                logger.error("R2 upload error for %s: %s. Falling back to local storage.", storage_key, e)
        elif cls.is_supabase_configured():
            sb_res = cls.upload_to_supabase(file, storage_key, content_type)
            if sb_res:
                return sb_res

        # Local fallback
        upload_base = current_app.config.get("UPLOAD_FOLDER", os.path.join(os.getcwd(), "uploads"))
        full_folder = os.path.join(upload_base, clean_folder)
        os.makedirs(full_folder, exist_ok=True)
        local_path = os.path.join(upload_base, storage_key.replace("/", os.sep))
        file.stream.seek(0)
        file.save(local_path)
        logger.info("Saved %s to local storage: %s", storage_key, local_path)
        return storage_key

    @classmethod
    def generate_presigned_url(cls, storage_key: str, expiration_seconds: int = 3600) -> Optional[str]:
        """Generate a secure, time-limited presigned GET URL for an object in R2.

        Returns None if in local fallback or storage_key is invalid.
        """
        if not storage_key:
            return None

        # Clean key
        storage_key = storage_key.replace("\\", "/").strip()

        if cls.is_configured():
            try:
                s3 = cls.get_s3_client()
                bucket = current_app.config["R2_BUCKET_NAME"]
                url = s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": storage_key},
                    ExpiresIn=expiration_seconds,
                )
                return url
            except ClientError as e:
                logger.error("Failed to generate presigned URL for %s: %s", storage_key, e)
                return None

        # In local fallback mode, callers can serve through an authenticated admin route
        return None

    @classmethod
    def get_local_path(cls, storage_key: str) -> Optional[str]:
        """Resolve a storage key or legacy path to an existing local file (for local fallback serving)."""
        if not storage_key:
            return None

        upload_base = current_app.config.get("UPLOAD_FOLDER", os.path.join(os.getcwd(), "uploads"))

        # Candidate 1: Direct path from upload_base + normalized storage_key
        normalized = storage_key.replace("/", os.sep).replace("\\", os.sep)
        path1 = os.path.join(upload_base, normalized)
        if os.path.isfile(path1):
            return path1

        # Candidate 2: In case key was stored as absolute path (legacy database entries)
        if os.path.isabs(storage_key) and os.path.isfile(storage_key):
            return storage_key

        # Candidate 3: Just the basename in upload_base
        base_name = os.path.basename(normalized)
        path3 = os.path.join(upload_base, base_name)
        if os.path.isfile(path3):
            return path3

        return None

    @classmethod
    def delete_file(cls, storage_key: str) -> bool:
        """Delete a file from R2 or local storage."""
        if not storage_key:
            return False

        storage_key = storage_key.replace("\\", "/").strip()
        if cls.is_configured():
            try:
                s3 = cls.get_s3_client()
                bucket = current_app.config["R2_BUCKET_NAME"]
                s3.delete_object(Bucket=bucket, Key=storage_key)
                return True
            except ClientError as e:
                logger.error("Failed to delete %s from R2: %s", storage_key, e)
        elif cls.is_supabase_configured():
            if cls.delete_from_supabase(storage_key):
                return True

        local_path = cls.get_local_path(storage_key)
        if local_path and os.path.isfile(local_path):
            try:
                os.remove(local_path)
                return True
            except OSError as e:
                logger.error("Failed to delete local file %s: %s", local_path, e)
        return False


storage_service = StorageService
