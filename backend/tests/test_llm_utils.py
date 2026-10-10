"""Structured-output repair and inference-budget regression tests."""
import asyncio
import time

import pytest
from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from app.config import settings
from app.llm_utils import invoke_llm_structured, parse_json_object


class SmallOutput(BaseModel):
    name: str
    count: int


class SlowRunnable(RunnableLambda):
    def with_structured_output(self, _schema):
        return self


def test_parse_json_object_repairs_fences_prose_and_trailing_commas():
    parsed = parse_json_object('Answer:\n```json\n{"name":"ok","items":[1,2,],}\n```')
    assert parsed == {"name": "ok", "items": [1, 2]}


@pytest.mark.asyncio
async def test_structured_invoke_validates_and_coerces_raw_json():
    llm = RunnableLambda(lambda _: AIMessage(content='Result: {"name":"ready","count":"2",}'))
    prompt = PromptTemplate.from_template("{format_instructions}")
    result = await invoke_llm_structured(
        llm,
        prompt,
        SmallOutput,
        {},
        format_instructions="Return JSON",
    )
    assert result == {"name": "ready", "count": 2}


@pytest.mark.asyncio
async def test_structured_invoke_obeys_shared_total_timeout(monkeypatch):
    async def slow(_):
        await asyncio.sleep(1)
        return AIMessage(content='{"name":"late","count":1}')

    llm = SlowRunnable(lambda _: None, afunc=slow)
    prompt = PromptTemplate.from_template("{format_instructions}")
    monkeypatch.setattr(settings, "LLM_REQUEST_TIMEOUT_SECONDS", 0.03)
    monkeypatch.setattr(settings, "LLM_STRUCTURED_TOTAL_TIMEOUT_SECONDS", 0.05)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="timed out before returning structured output"):
        await invoke_llm_structured(
            llm,
            prompt,
            SmallOutput,
            {},
            format_instructions="Return JSON",
        )
    assert time.monotonic() - started < 0.2
