import logging
import time
from dataclasses import dataclass, field

from . import images, llm, rules
from .rules import Issue

logger = logging.getLogger("invoices")

LLM_STATUS = {
    "timeout": 504,
    "rate_limit": 429,
    "auth": 502,
    "config": 500,
    "unavailable": 503,
    "refusal": 422,
    "truncated": 502,
    "invalid_response": 502,
    "bad_request": 502,
}

CORE_FIELDS = ("number", "date", "supplier.code", "supplier.iban", "total", "items")


class ProcessingError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class Result:
    decision: str
    reasons: list[str] = field(default_factory=list)
    document: dict | None = None
    issues: list[Issue] = field(default_factory=list)
    image: dict = field(default_factory=dict)
    model: str | None = None
    elapsed: dict = field(default_factory=dict)
    usage: dict | None = None
    raw: str | None = None


def _is_empty(document: dict) -> bool:
    return all(not rules._get(document, path) for path in CORE_FIELDS)


def decide(document: dict, issues: list[Issue]) -> tuple[str, list[str]]:
    type_issue = next((i for i in issues if i.rule == "document_type"), None)
    if type_issue:
        return "reject", [type_issue.message]
    if _is_empty(document):
        return "reject", ["З документа не вдалося прочитати жодного ключового поля."]

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    warning_lines = [f"Попередження, {i.field}: {i.message}" for i in warnings]

    if errors:
        return "review", [f"{i.field}: {i.message}" for i in errors] + warning_lines
    return "auto", ["Усі критичні поля на місці й пройшли перевірки."] + warning_lines


def process(content: bytes) -> Result:
    elapsed = {}

    started = time.perf_counter()
    try:
        image = images.prepare(content)
    except images.ImageError as exc:
        raise ProcessingError(str(exc), exc.status) from exc
    elapsed["prepare"] = time.perf_counter() - started

    started = time.perf_counter()
    try:
        extracted = llm.extract(image)
    except llm.LLMError as exc:
        raise ProcessingError(str(exc), LLM_STATUS.get(exc.kind, 502)) from exc
    elapsed["extraction"] = time.perf_counter() - started

    document = extracted["data"]

    started = time.perf_counter()
    issues = rules.check(document)
    elapsed["checks"] = time.perf_counter() - started

    decision, reasons = decide(document, issues)

    logger.info(
        "decision=%s errors=%d warnings=%d prepare=%.2fs extraction=%.2fs tokens=%s",
        decision,
        sum(1 for i in issues if i.severity == "error"),
        sum(1 for i in issues if i.severity == "warning"),
        elapsed["prepare"],
        elapsed["extraction"],
        (extracted["usage"] or {}).get("total_tokens"),
    )

    return Result(
        decision=decision,
        reasons=reasons,
        document=document,
        issues=issues,
        image={"original": image.original, "sent": image.sent, "sharpness": image.sharpness},
        model=extracted["model"],
        elapsed=elapsed,
        usage=extracted["usage"],
        raw=extracted["raw"],
    )