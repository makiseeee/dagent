import os
from collections.abc import Iterator

from openai import OpenAI
from dotenv import load_dotenv

from personal_agent.core.config.loader import LLMConfig


class LLMClient:
    def __init__(self, config: LLMConfig):
        load_dotenv()

        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("Missing DEEPSEEK_API_KEY in .env")

        self.client = OpenAI(
            api_key=api_key,
            base_url=config.base_url,
        )
        self.default_model = config.default_model

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        response = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            temperature=temperature,
        )

        content = response.choices[0].message.content
        return content or ""

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> Iterator[str]:
        response = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )

        for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)

            if content:
                yield content