FROM python:3.11-slim AS builder
WORKDIR /app
COPY chat_agent/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY shared.py lite_llm_agent.py jwt_utils.py ./
COPY chat_agent/main.py chat_agent/agent.py ./
CMD ["python", "main.py"]
