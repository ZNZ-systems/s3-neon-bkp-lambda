FROM public.ecr.aws/lambda/python:3.12

# Install PostgreSQL 16 client tools (pg_dump) from PGDG repo
# AL2023-based image uses dnf; PGDG EL-9 repo is compatible
RUN dnf install -y \
    https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-x86_64/pgdg-redhat-repo-latest.noarch.rpm && \
    dnf -qy module disable postgresql && \
    dnf install -y postgresql16 && \
    dnf clean all

# Ensure pg_dump is on PATH
ENV PATH="/usr/pgsql-16/bin:${PATH}"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py ./

CMD ["handler.lambda_handler"]
