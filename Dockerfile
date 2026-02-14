FROM public.ecr.aws/lambda/python:3.12

# Install gzip and PostgreSQL 15 client tools
RUN dnf install -y \
    gzip \
    postgresql15-contrib \
    && dnf clean all

# Copy requirements and handler
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
