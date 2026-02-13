import json
import os
import subprocess
import datetime

import boto3
from urllib.parse import urlparse, parse_qs

s3 = boto3.client("s3")
secrets_client = boto3.client("secretsmanager")


def get_database_configs():
    """Fetch database configurations from Secrets Manager."""
    secret_name = os.environ["SECRET_NAME"]
    response = secrets_client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    return secret["databases"]


def parse_database_url(db_url):
    """Parse a PostgreSQL connection URL into components."""
    parsed = urlparse(db_url)
    query_params = parse_qs(parsed.query)
    return {
        "host": parsed.hostname,
        "port": str(parsed.port or 5432),
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": parsed.password,
        "sslmode": query_params.get("sslmode", [None])[0],
    }


def run_backup(db_config, bucket, timestamp):
    """Run pg_dump for a single database and upload the gzipped dump to S3."""
    name = db_config["name"]
    db = parse_database_url(db_config["url"])

    filename = f"{timestamp}.sql.gz"
    s3_key = f"{name}/{filename}"
    local_path = f"/tmp/{name}_{filename}"

    env = os.environ.copy()
    if db["password"]:
        env["PGPASSWORD"] = db["password"]

    if db["sslmode"]:
        env["PGSSLMODE"] = db["sslmode"]

    dump_cmd = [
        "pg_dump",
        "-h", db["host"],
        "-p", db["port"],
        "-U", db["user"],
        "-d", db["dbname"],
        "--no-owner",
        "--no-privileges",
    ]

    # pg_dump | gzip > file
    with open(local_path, "wb") as f:
        dump_proc = subprocess.Popen(
            dump_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        gzip_proc = subprocess.Popen(
            ["gzip"],
            stdin=dump_proc.stdout,
            stdout=f,
            stderr=subprocess.PIPE,
        )
        # Allow dump_proc to receive SIGPIPE if gzip exits
        dump_proc.stdout.close()

        gzip_stderr = gzip_proc.communicate()[1]
        dump_returncode = dump_proc.wait()

        if dump_returncode != 0:
            dump_stderr = dump_proc.stderr.read().decode()
            raise Exception(f"pg_dump failed (exit {dump_returncode}): {dump_stderr}")
        if gzip_proc.returncode != 0:
            raise Exception(f"gzip failed: {gzip_stderr.decode()}")

    file_size = os.path.getsize(local_path)
    s3.upload_file(local_path, bucket, s3_key)
    os.remove(local_path)

    print(f"  Uploaded {file_size} bytes -> s3://{bucket}/{s3_key}")
    return f"s3://{bucket}/{s3_key}"


def lambda_handler(event, context):
    """Back up all configured Neon databases to S3."""
    bucket = os.environ["S3_BUCKET"]
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

    databases = get_database_configs()
    results = []

    for db_config in databases:
        name = db_config["name"]
        print(f"Starting backup: {name}")
        try:
            s3_path = run_backup(db_config, bucket, timestamp)
            results.append({"name": name, "status": "success", "path": s3_path})
            print(f"  SUCCESS: {name}")
        except Exception as e:
            results.append({"name": name, "status": "error", "message": str(e)})
            print(f"  ERROR: {name} -> {e}")

    succeeded = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "error"]
    print(f"Backup complete: {len(succeeded)} succeeded, {len(failed)} failed out of {len(results)} databases")

    if failed:
        raise Exception(
            f"{len(failed)} backup(s) failed: {json.dumps(failed)}"
        )

    return {"statusCode": 200, "results": results}
