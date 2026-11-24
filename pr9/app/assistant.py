"""Цикл помічника: модель → інструменти → модель, з обмеженням звертань."""

import json
import os
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

from . import llm, tools

load_dotenv()

MAX_ROUNDS = int(os.getenv("TOOL_MAX_ROUNDS", "3"))
LIMIT_TEXT = ("Вибачте, не вдалося завершити обробку питання за відведену кількість кроків. "
              "Спробуйте сформулювати питання простіше або конкретніше.")


@dataclass
class ToolTrace:
    round: int
    name: str
    arguments: str
    status: str
    reason: str | None = None
    result: dict | list | str | None = None
    elapsed: float | None = None


@dataclass
class Answer:
    text: str
    calls: list[ToolTrace] = field(default_factory=list)
    rounds: int = 0
    stopped: str = "answer"
    model: str | None = None
    elapsed: dict = field(default_factory=dict)
    usage: dict | None = None
    error_status: int | None = None  


def answer(question: str, customer_id: str) -> Answer:
    ctx = tools.Context(customer_id=customer_id)
    messages = llm.build_messages(question)
    specs = tools.specs()
    res = Answer(text="", elapsed={"model": 0.0, "tools": 0.0})
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    for rnd in range(1, MAX_ROUNDS + 1):
        forced = rnd == MAX_ROUNDS    
        try:
            r = llm.chat(messages, specs, "none" if forced else "auto")
        except llm.LLMError as e:
            res.text, res.stopped, res.error_status = e.user_message, "model_error", e.status
            res.usage = usage
            return res
        res.rounds = rnd
        res.model = r["model"]
        res.elapsed["model"] += r["elapsed"]
        if r["usage"]:
            usage["prompt_tokens"] += r["usage"]["prompt_tokens"] or 0
            usage["completion_tokens"] += r["usage"]["completion_tokens"] or 0

        msg = r["message"]
        calls = msg.get("tool_calls") or []
        if not calls or forced:
            text = (msg.get("content") or "").strip()
            if text and not (forced and calls):
                res.text, res.stopped = text, "answer"
            else:
                res.text, res.stopped = LIMIT_TEXT, "limit"
            break

        messages.append(msg) 
        mutated = False
        for tc in calls:
            fn = tc["function"]
            name, raw = fn.get("name", ""), fn.get("arguments", "")
            t0 = time.perf_counter()
            if tools.is_mutating(name) and mutated:
                result = tools.ToolResult(
                    "rejected",
                    {"error": "one_action", "message": "За одне звертання виконується лише одна змінююча дія."},
                    "друга змінююча дія в одному звертанні")
            else:
                result = tools.call(name, raw, ctx)
                mutated = mutated or (tools.is_mutating(name) and result.status == "ok")
            dt = time.perf_counter() - t0
            res.elapsed["tools"] += dt
            res.calls.append(ToolTrace(rnd, name, raw, result.status, result.reason, result.content, dt))
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": json.dumps(result.content, ensure_ascii=False)})
    res.usage = usage
    return res