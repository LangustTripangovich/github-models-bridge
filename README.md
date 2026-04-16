# GitHub Models Bridge

Python-клиент и HTTP-сервис для работы с [GitHub Models API](https://docs.github.com/en/github-models).

## Структура проекта

```
├── github_models.py   # Python-клиент (низкий уровень)
├── api.py             # FastAPI HTTP-сервис (для n8n и других интеграций)
├── examples.py        # Примеры использования клиента
├── requirements.txt
├── .env               # Токен (не коммитить!)
└── .env.example       # Шаблон
```

---

## Быстрый старт

### 1. Токен

Создай [GitHub PAT](https://github.com/settings/tokens):
- **Classic PAT** — достаточно создать, специальный scope не нужен
- **Fine-grained PAT** — добавь permission `Models → Read`

Положи в `.env`:
```
GITHUB_TOKEN=ghp_твой_токен
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

---

## Часть 1: Python-клиент

### Импорт и инициализация

```python
from github_models import GitHubModelsClient

# Токен читается из .env автоматически
client = GitHubModelsClient()

# Или явно
client = GitHubModelsClient(
    token="ghp_xxx",
    model="openai/gpt-4.1",   # модель по умолчанию
    timeout=120,               # таймаут запроса в секундах
    org="my-org",             # необязательно: attribution к организации
)
```

---

### Метод `chat()` — простой вопрос-ответ

Самый простой способ. Возвращает строку.

```python
reply = client.chat("Напиши функцию сортировки пузырьком")
print(reply)
```

**Все параметры:**

```python
reply = client.chat(
    user_message="твой вопрос",          # обязательный
    system_prompt="You are a helpful assistant.",  # системный промпт
    model="openai/gpt-4.1",              # переопределить модель
    temperature=0.2,                     # 0.0–1.0, меньше = детерминированнее
    max_tokens=2000,                     # макс. токенов в ответе
    json_mode=False,                     # True = ответ принудительно в JSON
)
```

---

### Метод `chat_json()` — ответ как dict

Автоматически включает JSON mode и парсит ответ.

```python
data = client.chat_json(
    user_message='Верни JSON: {"name": "...", "age": ...} для человека по имени Иван',
    system_prompt="Always respond with valid JSON.",
    temperature=0.1,
    max_tokens=500,
)
print(data["name"])  # "Иван"
```

---

### Метод `complete()` — полный контроль

Принимает список сообщений напрямую. Возвращает сырой response dict (как OpenAI API).

```python
response = client.complete(
    messages=[
        {"role": "system", "content": "You are a Python expert."},
        {"role": "user",   "content": "Что такое GIL?"},
        {"role": "assistant", "content": "GIL — это..."},   # история диалога
        {"role": "user",   "content": "А как его обойти?"},
    ],
    model="openai/gpt-4.1",
    temperature=0.3,
    max_tokens=1500,
    tools=[...],         # function calling (опционально)
    tool_choice="auto",  # "auto" | "required" | "none" | dict
    json_mode=False,
)

text = response["choices"][0]["message"]["content"]
```

**Структура response:**
```json
{
  "id": "chatcmpl-xxx",
  "model": "openai/gpt-4.1",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "текст ответа"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 45,
    "completion_tokens": 120,
    "total_tokens": 165
  }
}
```

---

### Метод `stream()` — стриминг

Возвращает генератор строк-чанков.

```python
messages = [{"role": "user", "content": "Расскажи историю"}]

for chunk in client.stream(messages, temperature=0.7, max_tokens=1000):
    print(chunk, end="", flush=True)
print()
```

---

### Метод `list_models()` — список моделей

```python
models = client.list_models()
for m in models:
    print(m["id"], "|", m["publisher"], "|", m.get("rate_limit_tier"))
```

**Пример одного объекта:**
```json
{
  "id": "openai/gpt-4.1",
  "name": "OpenAI GPT-4.1",
  "publisher": "OpenAI",
  "rate_limit_tier": "high",
  "capabilities": ["streaming", "tool-calling"],
  "limits": {
    "max_input_tokens": 1048576,
    "max_output_tokens": 32768
  },
  "supported_input_modalities": ["text", "image"],
  "supported_output_modalities": ["text"]
}
```

---

### Function Calling

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Получить погоду в городе",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                },
                "required": ["city"]
            }
        }
    }
]

response = client.complete(
    messages=[{"role": "user", "content": "Погода в Москве?"}],
    tools=tools,
    tool_choice="auto",
)

choice = response["choices"][0]
if choice["message"].get("tool_calls"):
    call = choice["message"]["tool_calls"][0]
    func_name = call["function"]["name"]          # "get_weather"
    func_args = json.loads(call["function"]["arguments"])  # {"city": "Москва"}
```

---

### Доступные модели

| ID | Описание |
|----|----------|
| `openai/gpt-4.1` | Лучший для кода и инструкций |
| `openai/gpt-4.1-mini` | Быстрее и дешевле |
| `openai/gpt-4o` | Мультимодальный |
| `openai/gpt-4o-mini` | Лёгкий и быстрый |
| `openai/gpt-5` | Самый мощный |
| `openai/o1`, `openai/o3-mini` | Reasoning-модели |
| `meta/llama-3.3-70b-instruct` | Open-source Llama |
| `mistral-ai/mistral-large-2411` | Mistral Large |
| `deepseek/deepseek-r1` | DeepSeek Reasoning |
| `xai/grok-3` | Grok от xAI |

Полный список: `client.list_models()`

---

## Часть 2: HTTP-сервис для n8n

Запускает FastAPI-сервер, который n8n дёргает через HTTP Request node.

### Запуск

```bash
python api.py
# Сервер стартует на http://localhost:8000
```

Или в фоне (продакшн):
```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

---

### Эндпоинты

#### `POST /chat` — простой чат

**Body:**
```json
{
  "message": "Напиши функцию на Python",
  "system_prompt": "You are a helpful assistant.",
  "model": "openai/gpt-4.1",
  "temperature": 0.2,
  "max_tokens": 2000
}
```

**Response:**
```json
{
  "reply": "Вот функция..."
}
```

---

#### `POST /complete` — полный контроль (история, tools)

**Body:**
```json
{
  "messages": [
    {"role": "system", "content": "You are a Python expert."},
    {"role": "user", "content": "Что такое GIL?"}
  ],
  "model": "openai/gpt-4.1",
  "temperature": 0.2,
  "max_tokens": 2000
}
```

**Response:** полный OpenAI-совместимый response object.

---

#### `POST /chat/json` — ответ в JSON

**Body:**
```json
{
  "message": "Верни данные о городе Москва в формате {\"city\": \"...\", \"population\": ...}",
  "system_prompt": "Always respond with valid JSON.",
  "temperature": 0.1
}
```

**Response:**
```json
{
  "result": {
    "city": "Москва",
    "population": 12500000
  }
}
```

---

#### `GET /models` — список доступных моделей

**Response:**
```json
[
  {"id": "openai/gpt-4.1", "name": "OpenAI GPT-4.1", "publisher": "OpenAI"},
  ...
]
```

---

#### `GET /health` — проверка работоспособности

```json
{"status": "ok"}
```

---

### Использование из n8n

#### Вариант A: n8n → HTTP Request → наш сервис

1. Добавь ноду **HTTP Request**
2. Method: `POST`
3. URL: `http://localhost:8000/chat` (или IP сервера)
4. Body: `JSON`
   ```json
   {
     "message": "{{ $json.user_input }}",
     "temperature": 0.2
   }
   ```
5. Ответ приходит в `$json.reply`

#### Вариант B: n8n Code Node (Python)

```python
from github_models import GitHubModelsClient

client = GitHubModelsClient(token="ghp_xxx")
reply = client.chat($input.first().json["user_input"])
return [{"reply": reply}]
```

---

## Лимиты GitHub Models (бесплатный тариф)

| Модели | Запросов/мин | Запросов/день |
|--------|-------------|--------------|
| Low tier (gpt-4o-mini и др.) | 15 | 150–300 |
| High tier (gpt-4.1, gpt-4o) | 10 | 50–100 |
| DeepSeek-R1, Grok-3 | 1–2 | 8–30 |

Лимиты зависят от уровня подписки Copilot (Free / Pro / Business / Enterprise).
