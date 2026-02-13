# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An AWS Lambda function that backs up Neon PostgreSQL databases to S3 on a schedule. Deployed as a Docker container via AWS SAM.

## Architecture

Single-file Lambda (`handler.py`) that:
1. Reads database connection URLs from AWS Secrets Manager (JSON with `databases` array of `{name, url}` objects)
2. Runs `pg_dump | gzip` via subprocess for each database
3. Uploads the gzipped dump to S3 under `{db-name}/{timestamp}.sql.gz`
4. Raises if any backup fails (so Lambda reports failure to CloudWatch)

PostgreSQL connection params (password, sslmode) are passed via libpq environment variables (`PGPASSWORD`, `PGSSLMODE`), not CLI flags — `pg_dump` doesn't accept `--sslmode` as a flag.

The Docker image (`Dockerfile`) is based on the AWS Lambda Python 3.12 runtime with PostgreSQL 16 client tools installed from PGDG.

## Commands

### Local test (requires local PostgreSQL and `pg_dump`)
```bash
python tests/test_local.py
```
Reads `DATABASE_URL` from `.env.test` (or override inline: `DATABASE_URL="..." python tests/test_local.py`). Mocks boto3 entirely — no AWS credentials needed. Backup output goes to `tests/backup_output/` (gitignored).

### Deploy
```bash
sam build
sam deploy              # uses samconfig.toml defaults (stack: neon-db-backup, us-east-1)
```
After first deploy, update the Secrets Manager secret with real Neon database URLs.

## Key Environment Variables

Lambda expects: `S3_BUCKET`, `SECRET_NAME` (set by SAM template).

## Testing Notes

- `.env.test` should include `?sslmode=prefer` in the URL to exercise the sslmode code path locally
- The test mocks S3 uploads by copying files to `tests/backup_output/` and verifies the dump contains valid PostgreSQL output
- `tests/init.sql` contains seed data for use with a disposable test database
