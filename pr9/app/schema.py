"""Контракт кроку розбору звернення."""

import json
import re

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

KINDS = ["return", "cancel", "status", "other", "unclear"]
REASONS = ["not_suitable", "defect", "wrong_item", "damaged", "none"]


class ParseError(ValueError):
    """Відповідь моделі не пройшла перевірку."""


def request_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": KINDS},
            "multiple_actions": {"type": "boolean"},
            "order_id": {"type": ["string", "null"]},
            "item": {"type": ["string", "null"]},
            "quantity": {"type": ["integer", "null"]},
            "reason": {"type": "string", "enum": REASONS},
            "reason_quote": {"type": ["string", "null"]},
        },
        "required": ["kind", "multiple_actions", "order_id", "item", "quantity",
                     "reason", "reason_quote"],
        "additionalProperties": False,
    }


_V = Draft202012Validator(request_schema())


def validate(raw: str, text: str | None = None) -> dict:
    """Схема + зміст: номер і цитата причини мають бути в тексті клієнта."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ParseError("відповідь не є JSON")
    err = best_match(_V.iter_errors(data))
    if err is not None:
        path = ".".join(str(p) for p in err.path) or "корінь"
        raise ParseError(f"{path}: {err.message}")

    for key in ("order_id", "item", "reason_quote"):
        if isinstance(data[key], str) and not data[key].strip():
            data[key] = None
    if data["item"]:
        data["item"] = data["item"].strip()

    if data["order_id"] is not None:
        digits = re.sub(r"\D", "", data["order_id"])
        if len(digits) != 5:
            raise ParseError("order_id має містити 5 цифр або бути null")
        if text is not None:
            compact = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
            if digits not in compact:
                raise ParseError("номера замовлення немає в тексті звернення; став null")
        data["order_id"] = digits

    if data["quantity"] is not None and not 1 <= data["quantity"] <= 20:
        raise ParseError("quantity має бути від 1 до 20 або null")

    if data["reason"] == "none":
        data["reason"], data["reason_quote"] = None, None
    else:
        quote = data["reason_quote"]
        if not quote or (text is not None and quote.lower() not in text.lower()):
            raise ParseError("reason_quote має бути дослівною цитатою зі звернення; "
                             "якщо причини немає — reason=none")
    return data


def choice_schema(skus: list[str]) -> dict:
    """Схема вибору товару: enum будується з позицій конкретного замовлення."""
    return {"type": "object",
            "properties": {"sku": {"type": "string", "enum": list(skus) + ["none"]}},
            "required": ["sku"], "additionalProperties": False}


def validate_choice(raw: str, skus: list[str]) -> str:
    try:
        sku = json.loads(raw)["sku"]
    except Exception:
        raise ParseError("відповідь не JSON зі полем sku")
    if sku not in list(skus) + ["none"]:
        raise ParseError(f"sku {sku!r} немає в замовленні")
    return sku