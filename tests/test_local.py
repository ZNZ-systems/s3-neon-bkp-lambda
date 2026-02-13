"""
Local test for the Neon backup Lambda handler.

Uses a local PostgreSQL database to verify pg_dump works correctly
and produces a valid gzipped SQL backup. No AWS dependencies needed —
boto3 is fully mocked so the test runs with zero external requirements.

Prerequisites:
    A running local PostgreSQL instance

Usage:
    python tests/test_local.py
    DATABASE_URL="postgresql://user@localhost:5432/mydb" python tests/test_local.py
"""

import gzip
import json
import os
import sys
import shutil
import types
from unittest.mock import MagicMock

# Point to project root so handler.py can be imported
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Load .env.test if DATABASE_URL is not already set
if "DATABASE_URL" not in os.environ:
    env_test_path = os.path.join(PROJECT_ROOT, ".env.test")
    if os.path.exists(env_test_path):
        with open(env_test_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value

LOCAL_DB_URL = os.environ.get("DATABASE_URL")
BACKUP_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "backup_output")


# --- Mock boto3 before handler.py is imported -----------------------------

mock_boto3 = types.ModuleType("boto3")
mock_botocore = types.ModuleType("botocore")
mock_botocore_exceptions = types.ModuleType("botocore.exceptions")
mock_botocore_exceptions.ClientError = type("ClientError", (Exception,), {})
mock_botocore.exceptions = mock_botocore_exceptions

mock_s3 = MagicMock()
mock_secrets = MagicMock()


def mock_client(service_name, **kwargs):
    if service_name == "s3":
        return mock_s3
    if service_name == "secretsmanager":
        return mock_secrets
    return MagicMock()


mock_boto3.client = mock_client
sys.modules["boto3"] = mock_boto3
sys.modules["botocore"] = mock_botocore
sys.modules["botocore.exceptions"] = mock_botocore_exceptions


# --- Configure mock responses ---------------------------------------------

def mock_get_secret_value(**kwargs):
    return {
        "SecretString": json.dumps({
            "databases": [
                {"name": "test-local-db", "url": LOCAL_DB_URL},
            ]
        })
    }


mock_secrets.get_secret_value.side_effect = mock_get_secret_value

uploaded_files: list[dict] = []


def mock_upload_file(local_path, bucket, s3_key):
    """Instead of uploading to S3, copy the backup file locally."""
    dest = os.path.join(BACKUP_OUTPUT_DIR, s3_key)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(local_path, dest)
    uploaded_files.append({"bucket": bucket, "key": s3_key, "local": dest})


mock_s3.upload_file.side_effect = mock_upload_file


# --- Test runner ----------------------------------------------------------

def main():
    os.makedirs(BACKUP_OUTPUT_DIR, exist_ok=True)

    # Set env vars the handler expects
    os.environ["S3_BUCKET"] = "test-bucket"
    os.environ["SECRET_NAME"] = "test-secret"

    # Now import handler — it will use our mocked boto3
    import handler

    print(f"Testing with DATABASE_URL: {LOCAL_DB_URL}")
    result = handler.lambda_handler({}, None)

    # ---- Verify results ----
    print("\n--- Results ---")
    print(json.dumps(result, indent=2))

    assert result["statusCode"] == 200, f"Expected 200, got {result['statusCode']}"
    assert len(result["results"]) == 1
    assert result["results"][0]["status"] == "success"

    # Verify the backup file
    assert len(uploaded_files) == 1
    backup_path = uploaded_files[0]["local"]
    file_size = os.path.getsize(backup_path)
    print(f"\nBackup file: {backup_path}")
    print(f"File size:   {file_size} bytes")

    assert file_size > 0, "Backup file is empty!"

    # Decompress and check it looks like a SQL dump
    with gzip.open(backup_path, "rt") as f:
        head = f.read(4096)

    assert "PostgreSQL database dump" in head, "Backup doesn't look like a pg_dump output"

    # Show first few lines
    print("\n--- Backup preview (first 20 lines) ---")
    for line in head.splitlines()[:20]:
        print(f"  {line}")

    print(f"\n=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    main()
