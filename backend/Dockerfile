FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY rag_chat_backend ./rag_chat_backend
RUN pip install --no-cache-dir ".[postgres]" && useradd -r -u 10001 app
USER app
EXPOSE 8080
CMD ["python", "-m", "rag_chat_backend.server"]
