"""
HTTP-сервис поверх GitHub Models API.
Запуск: python api.py
Продакшн: uvicorn api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from github_models import GitHubModelsClient, GitHubModelsError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(
    title="GitHub Models Bridge",
    description="HTTP-сервис для вызова GitHub Models API. Удобно использовать из n8n и других инструментов.",
    version="1.0.0",
)

# Один клиент на всё приложение (токен из .env)
_client: GitHubModelsClient | None = None


def get_client() -> GitHubModelsClient:
    global _client
    if _client is None:
        _client = GitHubModelsClient()
    return _client


# ---------------------------------------------------------------------------
# Схемы запросов
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(..., description="Сообщение пользователя")
    system_prompt: str = Field(
        default="You are a helpful assistant.",
        description="Системный промпт",
    )
    model: str = Field(default="openai/gpt-4.1", description="ID модели: publisher/model_name")
    temperature: float = Field(default=0.2, ge=0.0, le=1.0, description="0.0–1.0")
    max_tokens: int = Field(default=2000, gt=0, le=32768)


class ChatJsonRequest(BaseModel):
    message: str = Field(..., description="Сообщение пользователя")
    system_prompt: str = Field(
        default="You are a helpful assistant. Always respond with valid JSON.",
        description="Системный промпт. Должен требовать JSON-ответ.",
    )
    model: str = Field(default="openai/gpt-4.1")
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2000, gt=0, le=32768)


class Message(BaseModel):
    role: str = Field(..., description="system | user | assistant | tool")
    content: str | None = None
    tool_call_id: str | None = None
    name: str | None = None


class CompleteRequest(BaseModel):
    messages: list[Message] = Field(..., description="История сообщений")
    model: str = Field(default="openai/gpt-4.1")
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2000, gt=0, le=32768)
    tools: list[dict] | None = Field(default=None, description="Список инструментов для function calling")
    tool_choice: str | dict | None = Field(default=None, description="auto | required | none | dict")
    json_mode: bool = Field(default=False, description="Принудительный JSON-ответ")


class StreamRequest(BaseModel):
    messages: list[Message] = Field(..., description="История сообщений")
    model: str = Field(default="openai/gpt-4.1")
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2000, gt=0, le=32768)


# ---------------------------------------------------------------------------
# Вспомогательная функция
# ---------------------------------------------------------------------------


def _handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GitHubModelsError):
        status = exc.status_code or 502
        return HTTPException(status_code=status, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    log.exception("Unexpected error")
    return HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------


@app.get("/health", tags=["service"])
def health() -> dict:
    """Проверка работоспособности сервиса."""
    return {"status": "ok"}


@app.get("/models", tags=["catalog"])
def list_models() -> list[dict]:
    """Список всех доступных моделей GitHub Models."""
    try:
        return get_client().list_models()
    except Exception as exc:
        raise _handle_error(exc) from exc


@app.post("/chat", tags=["inference"])
def chat(req: ChatRequest) -> dict[str, str]:
    """
    Простой вопрос-ответ. Возвращает `{"reply": "..."}`.

    Удобно для n8n HTTP Request node — ответ сразу в `$json.reply`.
    """
    try:
        reply = get_client().chat(
            user_message=req.message,
            system_prompt=req.system_prompt,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return {"reply": reply}
    except Exception as exc:
        raise _handle_error(exc) from exc


@app.post("/chat/json", tags=["inference"])
def chat_json(req: ChatJsonRequest) -> dict[str, Any]:
    """
    Чат с принудительным JSON-ответом от модели.
    Возвращает `{"result": {...}}` где result — распарсенный JSON от модели.
    """
    try:
        result = get_client().chat_json(
            user_message=req.message,
            system_prompt=req.system_prompt,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return {"result": result}
    except Exception as exc:
        raise _handle_error(exc) from exc


@app.post("/complete", tags=["inference"])
def complete(req: CompleteRequest) -> dict:
    """
    Полный chat completions вызов. Принимает историю сообщений, поддерживает
    function calling и JSON mode. Возвращает сырой OpenAI-совместимый response.
    """
    try:
        messages = [m.model_dump(exclude_none=True) for m in req.messages]
        return get_client().complete(
            messages=messages,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            tools=req.tools,
            tool_choice=req.tool_choice,
            json_mode=req.json_mode,
        )
    except Exception as exc:
        raise _handle_error(exc) from exc


@app.post("/stream", tags=["inference"])
def stream(req: StreamRequest) -> StreamingResponse:
    """
    Стриминг ответа (Server-Sent Events).
    Каждая строка: `data: <chunk>\\n\\n`, финал: `data: [DONE]\\n\\n`

    Для n8n: лучше использовать /chat — стриминг там не нужен.
    """
    messages = [m.model_dump(exclude_none=True) for m in req.messages]

    def generate():
        try:
            for chunk in get_client().stream(
                messages=messages,
                model=req.model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: [ERROR] {exc}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
