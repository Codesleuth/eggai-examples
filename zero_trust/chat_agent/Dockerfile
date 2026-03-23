FROM python:3.11-slim AS builder
WORKDIR /app
COPY chat_agent/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY chat_agent/*.py ./
CMD ["python", "main.py"]
