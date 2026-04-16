FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY github_models.py .
COPY api.py .

# Токен пробрасывается через env var при запуске контейнера
ENV GITHUB_TOKEN=""

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
