FROM python:3.11-slim
WORKDIR /app
COPY chat_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared.py lite_llm_agent.py jwt_utils.py ./
COPY chat_agent/main.py chat_agent/agent.py ./
CMD ["python", "main.py"]
