FROM python:3.11-slim AS builder

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com .

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /install /usr/local

COPY src/ src/
COPY server.py pr.py pr-review.yaml ./
COPY skills/ skills/
COPY templates/ templates/

VOLUME ["/app/.pr_reviews"]
EXPOSE 8000

CMD ["python", "server.py"]
