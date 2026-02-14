FROM public.ecr.aws/lambda/python:3.12

# Install gzip and PostgreSQL 16 client tools from AL2023 repos
# For PG 17 server compatibility: pg_dump 16 is close enough for most backups
# For strict version matching, update this to pg_dump 17 when available in AL2023
RUN dnf install -y gzip postgresql16 && \
    dnf clean all

# Ensure pg_dump is on PATH
ENV PATH="/usr/pgsql-16/bin:${PATH}"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py ./

CMD ["handler.lambda_handler"]
