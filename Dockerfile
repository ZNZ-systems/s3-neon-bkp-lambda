FROM public.ecr.aws/lambda/python:3.12

# Install gzip for backup compression
RUN dnf install -y gzip && dnf clean all

# Copy pre-built PostgreSQL 17 client binaries (built on AL2023 for compatibility)
COPY bin/postgres-17.8/pg_dump /usr/local/bin/pg_dump
COPY bin/postgres-17.8/pg_restore /usr/local/bin/pg_restore
COPY bin/postgres-17.8/libpq.so.5 /usr/lib64/libpq.so.5

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
