import re
import time
from dataclasses import dataclass, field

from .index import SearchIndex
from .keyword import KeywordIndex
from . import retrieval, llm
from .retrieval import Source

NO_INFO_TEXT = (
    "На жаль, у базі знань немає інформації для відповіді на ваше запитання. "
    "Спробуйте переформулювати питання або зверніться до оператора."
)
UNVERIFIED_TEXT = (
    "Не вдалося підтвердити відповідь за джерелами. "
    "Спробуйте переформулювати запит або зверніться до оператора."
)


@dataclass
class Answer:
    text: str
    found: bool
    sources: list[Source] = field(default_factory=list)
    retrieved: list[Source] = field(default_factory=list)
    model: str | None = None
    elapsed: dict = field(default_factory=dict)
    usage: dict | None = None
    warning: str | None = None


def _source_to_dict(source: Source) -> dict:
    return {
        "ref": source.ref,
        "score": source.score,
        "text": source.chunk.text,
        "source": source.chunk.source,
        "metadata": source.chunk.metadata,
    }


def answer_to_dict(result: Answer) -> dict:
    return {
        "answer": result.text,
        "found": result.found,
        "sources": [_source_to_dict(s) for s in result.sources],
        "retrieved": [_source_to_dict(s) for s in result.retrieved],
        "model": result.model,
        "elapsed": result.elapsed,
        "usage": result.usage,
        "warning": result.warning,
    }


def _normalize_numbers(text: str) -> set[str]:
    text = re.sub(r"\[\d+\]", " ", text)
    text = re.sub(r"(?<=\d)[\s\u00a0](?=\d{3}\b)", "", text)
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def _numbers_supported(answer_text: str, cited: list[Source]) -> bool:
    answer_numbers = _normalize_numbers(answer_text)
    if not answer_numbers:
        return True
    source_numbers: set[str] = set()
    for s in cited:
        source_numbers |= _normalize_numbers(s.chunk.text)
        source_numbers |= _normalize_numbers(" ".join(str(v) for v in s.chunk.metadata.values()))
    return answer_numbers <= source_numbers


def answer(
    question: str,
    index: SearchIndex,
    keyword_index: KeywordIndex | None,
    filters: dict | None = None,
) -> Answer:
    t0 = time.perf_counter()
    hits = retrieval.retrieve(question, index, keyword_index, filters)
    retrieval_time = time.perf_counter() - t0

    if not hits:
        return Answer(text=NO_INFO_TEXT, found=False, elapsed={"retrieval": retrieval_time})

    context_text, context_sources = retrieval.build_context(hits)
    if not context_text or not context_sources:
        return Answer(text=NO_INFO_TEXT, found=False, elapsed={"retrieval": retrieval_time})

    t1 = time.perf_counter()
    llm_response = llm.ask(question, context_text)
    gen_time = time.perf_counter() - t1

    parsed = llm_response["parsed"]
    valid_refs = {s.ref: s for s in context_sources}
    elapsed = {"retrieval": retrieval_time, "generation": gen_time}
    answer_text = (parsed.get("answer") or "").strip()
    model_found = bool(parsed.get("found"))
    raw_refs = parsed.get("sources", [])
    final_sources = [valid_refs[r] for r in dict.fromkeys(raw_refs) if r in valid_refs]
    invalid_refs = [r for r in raw_refs if r not in valid_refs]

    base = dict(
        retrieved=context_sources,
        model=llm_response["model"],
        elapsed=elapsed,
        usage=llm_response.get("usage"),
    )

    if not model_found:
        return Answer(text=answer_text or NO_INFO_TEXT, found=False, **base)

    if not answer_text:
        return Answer(text=NO_INFO_TEXT, found=False, **base)

    if not final_sources:
        return Answer(text=UNVERIFIED_TEXT, found=False, warning="found без дійсних джерел", **base)

    warning = f"недійсні номери джерел: {invalid_refs}" if invalid_refs else None

    if not _numbers_supported(answer_text, final_sources):
        return Answer(
            text=UNVERIFIED_TEXT,
            found=False,
            sources=final_sources,
            warning="число у відповіді відсутнє в процитованих фрагментах",
            **base,
        )

    return Answer(text=answer_text, found=True, sources=final_sources, warning=warning, **base)