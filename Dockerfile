FROM public.ecr.aws/lambda/python:3.12

# Install PostgreSQL client tools from AL2023 repos
# Uses PostgreSQL 15 client for broad compatibility with most PG versions
RUN dnf install -y postgresql15 && \
    dnf clean all

# Ensure pg_dump is on PATH
ENV PATH="/usr/pgsql-15/bin:${PATH}"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py ./

CMD ["handler.lambda_handler"]
