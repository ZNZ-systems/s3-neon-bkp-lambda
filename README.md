# neon-s3-backup

Automated, scheduled backups of your [Neon](https://neon.tech) PostgreSQL databases to S3 — powered by a single Lambda function.

One `sam deploy` gives you nightly gzipped `pg_dump` backups, AES-256 encrypted at rest, with automatic lifecycle expiration. No servers to manage, no cron jobs to babysit.

## Why

Neon has point-in-time restore, but it's tied to your Neon project. If you want an independent, portable copy of your data sitting in your own AWS account — this is the simplest way to get it.

- **~150 lines of Python** — easy to audit, easy to fork
- **Backs up multiple databases** in a single invocation
- **Gzipped `pg_dump`** output — standard SQL format, restore anywhere
- **Zero dependencies** beyond `boto3` (included in Lambda) and `pg_dump` (installed in the Docker image)

## How It Works

```
EventBridge (cron)
    └─▶ Lambda (Docker: Python 3.12 + pg_dump 15)
            ├─ Reads database URLs from Secrets Manager
            ├─ Runs: pg_dump | gzip  (for each database)
            └─ Uploads to S3: {db-name}/{timestamp}.sql.gz
```

The Lambda fetches connection URLs from a single Secrets Manager secret, runs `pg_dump` piped through `gzip` for each database, uploads the result to an encrypted S3 bucket, then cleans up. If any backup fails, the Lambda raises so CloudWatch can alert you.

### ⚠️ PostgreSQL Version Compatibility

This project uses **PostgreSQL 15 client tools** (latest available in AWS Lambda AL2023). PostgreSQL's `pg_dump` enforces strict version compatibility:

- ✅ Works with: PostgreSQL 14, 15, 16 (same major or one version older)
- ❌ Fails with: PostgreSQL 17+ (`pg_dump: error: aborting because of server version mismatch`)

**For Neon databases running PostgreSQL 17:** This Lambda will fail due to pg_dump version mismatch. Consider these alternatives:
1. **Use GitHub Actions instead** — See [neon/neon-multiple-db-s3-backups](https://github.com/neondatabase/neon-multiple-db-s3-backups) for a CI/CD approach with flexible tooling
2. **Wait for AL2023 to include PostgreSQL 17** — Update the Dockerfile when available
3. **Fork this repo** — Build PostgreSQL 17 from source in the Dockerfile (adds ~2 min to build time)

## S3 Layout

```
my-backup-bucket/
├── my-app-prod/
│   ├── 2025-01-15_02-00-00.sql.gz
│   ├── 2025-01-16_02-00-00.sql.gz
│   └── ...
├── my-app-staging/
│   ├── 2025-01-15_02-00-00.sql.gz
│   └── ...
```

## Prerequisites

- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Docker (for building the Lambda container image)
- AWS credentials configured (`aws configure` or environment variables)

## Deploy

```bash
sam build
sam deploy --guided   # first time — walks you through the parameters
sam deploy            # subsequent deploys use saved config in samconfig.toml
```

### Parameters

| Parameter | Default | Description |
|---|---|---|
| `Schedule` | `cron(0 2 * * ? *)` | EventBridge schedule expression (default: 2 AM UTC daily) |
| `BackupRetentionDays` | `30` | Days to keep backups before S3 lifecycle deletes them |

### After Deploying

Update the Secrets Manager secret with your real Neon database URLs:

```bash
aws secretsmanager put-secret-value \
  --secret-id neon-db-backup-urls \
  --secret-string '{
    "databases": [
      {
        "name": "my-app-prod",
        "url": "postgresql://user:password@ep-cool-rain-123456.us-east-2.aws.neon.tech/neondb?sslmode=require"
      },
      {
        "name": "my-app-staging",
        "url": "postgresql://user:password@ep-wild-fire-654321.us-east-2.aws.neon.tech/neondb?sslmode=require"
      }
    ]
  }'
```

Each entry needs:
- **`name`** — a label for the database (used as the S3 folder name)
- **`url`** — a full PostgreSQL connection URL (Neon's dashboard gives you this)

### Test It Manually

Trigger a backup without waiting for the schedule:

```bash
aws lambda invoke \
  --function-name $(aws cloudformation describe-stacks \
    --stack-name neon-db-backup \
    --query 'Stacks[0].Outputs[?OutputKey==`BackupFunctionArn`].OutputValue' \
    --output text) \
  /dev/stdout
```

## Restore

Download and decompress a backup, then restore with `psql`:

```bash
# Download
aws s3 cp s3://YOUR_BUCKET/my-app-prod/2025-01-15_02-00-00.sql.gz .

# Decompress
gunzip 2025-01-15_02-00-00.sql.gz

# Restore to a new database
psql "postgresql://user:password@ep-your-endpoint.aws.neon.tech/new_db?sslmode=require" \
  < 2025-01-15_02-00-00.sql
```

## Local Development

### Prerequisites

- Python 3.12+
- PostgreSQL client tools (`pg_dump`) — install via `brew install postgresql` / `apt install postgresql-client`
- A running local PostgreSQL instance

### Setup

```bash
# Create .env.test with your local database URL
cat > .env.test << 'EOF'
DATABASE_URL=postgresql://youruser@localhost:5432/yourdb?sslmode=prefer
EOF
```

### Run the Test

```bash
python tests/test_local.py
```

This mocks all AWS services (S3, Secrets Manager) and runs the full backup pipeline against your local database. The gzipped dump is saved to `tests/backup_output/` for inspection. No AWS credentials needed.

You can also override the database URL inline:

```bash
DATABASE_URL="postgresql://user@localhost:5432/otherdb" python tests/test_local.py
```

A successful run looks like:

```
Testing with DATABASE_URL: postgresql://youruser@localhost:5432/yourdb?sslmode=prefer
Starting backup: test-local-db
  Uploaded 7506 bytes -> s3://test-bucket/test-local-db/2025-01-15_20-42-33.sql.gz
  SUCCESS: test-local-db
Backup complete: 1 succeeded, 0 failed out of 1 databases

=== ALL CHECKS PASSED ===
```

## Infrastructure

Everything is defined in `template.yaml` (AWS SAM / CloudFormation):

| Resource | What it does |
|---|---|
| **S3 Bucket** | Stores backups. AES-256 encryption, all public access blocked, lifecycle policy auto-deletes after N days. |
| **Secrets Manager Secret** | Holds database connection URLs. Update after deploy with your real Neon URLs. |
| **Lambda Function** | Docker container (Python 3.12 + PostgreSQL 16 client). Runs `pg_dump \| gzip` and uploads to S3. 15-minute timeout, 512 MB memory, 1 GB ephemeral storage. |
| **EventBridge Rule** | Triggers the Lambda on a cron schedule. |

## Cost

This is extremely cheap to run:

- **Lambda** — a typical backup takes seconds. Well within free tier, and pennies beyond it.
- **S3** — gzipped SQL dumps are small. A 100 MB database compresses to roughly 5-10 MB.
- **Secrets Manager** — ~$0.40/month per secret.

## Project Structure

```
├── handler.py          # Lambda function — the entire backup logic
├── Dockerfile          # Lambda container image (Python 3.12 + pg_dump 16)
├── template.yaml       # SAM/CloudFormation infrastructure
├── samconfig.toml      # SAM deploy configuration
├── requirements.txt    # Python dependencies (just boto3)
├── .env.test           # Local test database URL (not committed)
└── tests/
    ├── test_local.py   # Local test runner (mocks AWS, runs real pg_dump)
    └── init.sql        # Sample seed data for a test database
```

## License

MIT
