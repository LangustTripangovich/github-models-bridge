"""
GitHub Models API client.
Docs: https://docs.github.com/en/github-models
"""

import os
import json
import time
import logging
from typing import Iterator

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()  # читает .env из текущей директории (и выше по дереву)
except ImportError:
    pass  # python-dotenv не установлен — ничего страшного

log = logging.getLogger(__name__)

GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"
DEFAULT_MODEL = "openai/gpt-4.1"
DEFAULT_TIMEOUT = 120


class GitHubModelsError(Exception):
    def __init__(self, message: str, status_code: int | None = None, response_body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GitHubModelsClient:
    """
    Minimal client for GitHub Models inference API.

    Usage:
        client = GitHubModelsClient()                     # reads GITHUB_TOKEN from env
        client = GitHubModelsClient(token="ghp_xxx...")   # explicit token

    Basic call:
        reply = client.chat("Напиши функцию сортировки пузырьком")

    Low-level call (full messages list):
        response = client.complete([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user",   "content": "Hello"},
        ])
    """

    def __init__(
        self,
        token: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
        org: str | None = None,
    ):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError(
                "GitHub token required. Set GITHUB_TOKEN env var or pass token= explicitly."
            )
        self.model = model
        self.timeout = timeout

        if org:
            self.base_url = f"https://models.github.ai/orgs/{org}/inference/chat/completions"
        else:
            self.base_url = GITHUB_MODELS_URL

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def chat(
        self,
        user_message: str,
        system_prompt: str = "You are a helpful assistant.",
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        """One-shot: send a single user message, get back a string reply."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        response = self.complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        return response["choices"][0]["message"]["content"]

    def chat_json(
        self,
        user_message: str,
        system_prompt: str = "You are a helpful assistant. Always respond with valid JSON.",
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> dict:
        """
        Like chat(), but forces JSON mode and parses the response automatically.
        The model is instructed to return JSON via the system prompt.
        """
        text = self.chat(
            user_message,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise GitHubModelsError(
                f"Model returned non-JSON content: {text[:200]}"
            ) from exc

    def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        json_mode: bool = False,
    ) -> dict:
        """
        Full chat completions call. Returns the raw response dict.
        Identical to the OpenAI chat.completions.create() response shape.
        """
        payload: dict = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        return self._post(payload)

    def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> Iterator[str]:
        """
        Streaming variant. Yields text chunks as they arrive.

        Example:
            for chunk in client.stream([{"role": "user", "content": "Tell me a story"}]):
                print(chunk, end="", flush=True)
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        with self._session.post(
            self.base_url, json=payload, timeout=self.timeout, stream=True
        ) as resp:
            self._raise_for_status(resp)
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"]
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    def list_models(self) -> list[dict]:
        """
        Return available models from the GitHub Models catalog.
        Each dict has at minimum: id, name, publisher.
        """
        resp = self._session.get(
            "https://models.github.ai/catalog/models",
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        data = resp.json()
        # API may return {"models": [...]} or a plain list
        if isinstance(data, list):
            return data
        return data.get("models", data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(self, payload: dict, retries: int = 3) -> dict:
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = self._session.post(
                    self.base_url,
                    json=payload,
                    timeout=self.timeout,
                )
                self._raise_for_status(resp)
                return resp.json()
            except requests.exceptions.Timeout as exc:
                last_exc = exc
                log.warning("Request timed out (attempt %d/%d)", attempt + 1, retries)
            except GitHubModelsError as exc:
                # Don't retry client errors (4xx)
                if exc.status_code and exc.status_code < 500:
                    raise
                last_exc = exc
                log.warning(
                    "Server error %s (attempt %d/%d)", exc.status_code, attempt + 1, retries
                )
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s back-off
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        if resp.status_code < 400:
            return
        hints = {
            401: "Bad token. Make sure GITHUB_TOKEN is valid.",
            403: "Access denied. Check that your token has 'models: read' scope "
                 "(for fine-grained PAT) or that GitHub Models is enabled for your account.",
            404: "Endpoint not found. Check the model ID format: publisher/model_name.",
            422: "Invalid request payload. Check messages format and model name.",
            429: "Rate limit hit. Wait a bit and retry.",
        }
        body = ""
        try:
            body = resp.text
        except Exception:
            pass
        hint = hints.get(resp.status_code, "")
        msg = f"HTTP {resp.status_code}"
        if hint:
            msg += f" — {hint}"
        if body:
            msg += f"\nResponse: {body[:400]}"
        raise GitHubModelsError(msg, status_code=resp.status_code, response_body=body)
