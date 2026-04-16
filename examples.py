"""
Примеры использования GitHub Models API.
Запуск: python examples.py

Нужно заранее:
    set GITHUB_TOKEN=ghp_ваш_токен     (Windows)
    export GITHUB_TOKEN=ghp_ваш_токен  (Linux/macOS)
"""

import json
from github_models import GitHubModelsClient


def demo_simple_chat():
    """Пример 1: простой вопрос-ответ."""
    print("=" * 60)
    print("Пример 1: простой чат")
    print("=" * 60)

    client = GitHubModelsClient()
    reply = client.chat("Напиши функцию на Python которая проверяет является ли строка палиндромом")
    print(reply)


def demo_json_mode():
    """Пример 2: получить ответ в виде JSON."""
    print("\n" + "=" * 60)
    print("Пример 2: JSON mode")
    print("=" * 60)

    client = GitHubModelsClient()
    data = client.chat_json(
        user_message="Верни JSON со списком 3 популярных Python библиотек для работы с HTTP. "
                     'Формат: {"libraries": [{"name": "...", "description": "..."}]}',
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


def demo_streaming():
    """Пример 3: стриминг (чанки прилетают по мере генерации)."""
    print("\n" + "=" * 60)
    print("Пример 3: streaming")
    print("=" * 60)

    client = GitHubModelsClient()
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Объясни кратко что такое async/await в Python"},
    ]
    for chunk in client.stream(messages):
        print(chunk, end="", flush=True)
    print()  # новая строка после окончания


def demo_function_calling():
    """Пример 4: function calling (tool use)."""
    print("\n" + "=" * 60)
    print("Пример 4: function calling")
    print("=" * 60)

    client = GitHubModelsClient()

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Получить текущую погоду в городе",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "Название города",
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Единица измерения температуры",
                        },
                    },
                    "required": ["city"],
                },
            },
        }
    ]

    messages = [
        {"role": "user", "content": "Какая сейчас погода в Москве?"},
    ]

    response = client.complete(messages, tools=tools, tool_choice="auto")
    choice = response["choices"][0]
    message = choice["message"]

    if message.get("tool_calls"):
        call = message["tool_calls"][0]
        func_name = call["function"]["name"]
        func_args = json.loads(call["function"]["arguments"])
        print(f"Модель вызвала функцию: {func_name}({func_args})")

        # Имитируем ответ инструмента и продолжаем диалог
        messages.append(message)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps({"city": func_args["city"], "temperature": 12, "unit": "celsius", "description": "Облачно"}),
            }
        )
        final = client.complete(messages, tools=tools)
        print(final["choices"][0]["message"]["content"])
    else:
        print(message["content"])


def demo_list_models():
    """Пример 5: список доступных моделей."""
    print("\n" + "=" * 60)
    print("Пример 5: доступные модели")
    print("=" * 60)

    client = GitHubModelsClient()
    try:
        models = client.list_models()
        for m in models[:10]:  # показываем первые 10
            name = m.get("id") or m.get("name", "?")
            publisher = m.get("publisher", "")
            print(f"  {publisher}/{name}" if publisher else f"  {name}")
        if len(models) > 10:
            print(f"  ... и ещё {len(models) - 10} моделей")
    except Exception as exc:
        print(f"Не удалось получить список моделей: {exc}")


def demo_multi_turn():
    """Пример 6: многоходовой диалог (история сообщений вручную)."""
    print("\n" + "=" * 60)
    print("Пример 6: многоходовой диалог")
    print("=" * 60)

    client = GitHubModelsClient()
    history: list[dict] = [
        {"role": "system", "content": "You are a helpful Python tutor."},
    ]

    turns = [
        "Что такое list comprehension?",
        "Дай пример с условием if внутри",
        "А как сделать то же самое через filter()?",
    ]

    for user_text in turns:
        history.append({"role": "user", "content": user_text})
        print(f"\nПользователь: {user_text}")
        response = client.complete(history)
        reply = response["choices"][0]["message"]["content"]
        history.append({"role": "assistant", "content": reply})
        print(f"Ассистент: {reply}")


if __name__ == "__main__":
    import sys

    demos = {
        "1": demo_simple_chat,
        "2": demo_json_mode,
        "3": demo_streaming,
        "4": demo_function_calling,
        "5": demo_list_models,
        "6": demo_multi_turn,
    }

    if len(sys.argv) > 1:
        key = sys.argv[1]
        if key in demos:
            demos[key]()
        else:
            print(f"Неизвестный номер примера: {key}. Доступны: {list(demos.keys())}")
    else:
        print("Запускаю все примеры по порядку...\n")
        for fn in demos.values():
            try:
                fn()
            except Exception as exc:
                print(f"[ОШИБКА] {exc}")
