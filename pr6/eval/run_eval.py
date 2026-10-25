import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app import index, keyword, llm, rag

HERE = Path(__file__).parent
QUESTIONS_FILE = HERE / "questions.json"
INDEX_PATH = ROOT / "data" / "index.pkl"
DELAY = float(os.getenv("EVAL_DELAY", "4"))


def norm(text) -> str:
    text = str(text).replace("\u00a0", " ")
    text = re.sub(r"(?<=\d)\s(?=\d{3}\b)", "", text)
    return text.lower()


def has_fact(fact, text: str) -> bool:
    pattern = r"(?<![\w.,])" + re.escape(norm(fact)) + r"(?![\w])"
    return re.search(pattern, text) is not None


def load_questions() -> list[dict]:
    if not QUESTIONS_FILE.exists():
        print("Створіть eval/questions.json.")
        sys.exit(1)
    data = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    return data["питання"]


def ask(question, idx, kw, filters):
    err = ""
    for attempt in range(2):
        try:
            return rag.answer(question, idx, kw, filters or None), None
        except llm.LLMError as exc:
            err = str(exc)
            if attempt == 0 and "ліміт" in err.lower():
                time.sleep(30)
                continue
            return None, err
        except Exception as exc:
            return None, repr(exc)
    return None, err


def classify(item, answer, error):
    expect = item.get("очікується_відповідь", True)
    docs = item.get("очікувані_документи", [])
    facts = item.get("очікувані_факти", [])
    banned = item.get("заборонено", [])

    if error:
        return "помилка", error

    ctx = answer.retrieved
    ctx_docs = {s.chunk.source for s in ctx}

    if any(s.chunk.metadata.get("audience") == "персонал" for s in ctx):
        return "пошук", "витік"
    if any(s.chunk.metadata.get("status") == "архів" for s in ctx):
        return "пошук", "не та редакція"

    text = norm(answer.text)
    if any(norm(b) in text for b in banned):
        return "модель", "заборонений факт у відповіді"

    if expect:
        missing = [d for d in docs if d not in ctx_docs]
        if missing:
            return "пошук", "не знайдено: " + ", ".join(missing)
        ctx_text = norm(" ".join(s.chunk.text for s in ctx))
        no_fact = [f for f in facts if not has_fact(f, ctx_text)]
        if no_fact:
            return "пошук", "факту немає в контексті: " + ", ".join(no_fact)
        if not answer.found:
            return "модель", "безпідставна відмова"
        if not answer.sources:
            return "модель", "хибне посилання"
        lacking = [f for f in facts if not has_fact(f, text)]
        if lacking:
            return "модель", "немає фактів: " + ", ".join(lacking)
    elif answer.found:
        return "модель", "відповідь без підстав"

    return None, None


def run(label: str) -> int:
    if not INDEX_PATH.exists():
        print("Індекс не знайдено. Запустіть python ingest.py")
        return 1

    idx = index.load(INDEX_PATH)
    kw = keyword.build(idx.chunks)
    idx.search("тест", top_k=1)
    questions = load_questions()
    results = []

    for i, item in enumerate(questions, start=1):
        q = item["питання"]
        filters = item.get("фільтри") or {}
        expect = item.get("очікується_відповідь", True)
        docs = item.get("очікувані_документи", [])

        answer, error = ask(q, idx, kw, filters)
        stage, ftype = classify(item, answer, error)

        record = {
            "num": i,
            "вид": item.get("вид"),
            "question": q,
            "filters": filters,
            "expect_answer": expect,
            "expected_docs": docs,
            "failure_stage": stage,
            "failure_type": ftype,
        }
        if answer is not None:
            ctx_docs = {s.chunk.source for s in answer.retrieved}
            record.update({
                "found": answer.found,
                "answer": answer.text,
                "warning": answer.warning,
                "cited": [s.ref for s in answer.sources],
                "doc_in_context": all(d in ctx_docs for d in docs),
                "context": [
                    {
                        "ref": s.ref,
                        "source": s.chunk.source,
                        "heading": s.chunk.metadata.get("heading"),
                        "score": round(s.score, 4),
                        "text": s.chunk.text,
                    }
                    for s in answer.retrieved
                ],
                "elapsed": answer.elapsed,
                "usage": answer.usage,
            })
        else:
            record.update({"found": None, "answer": None, "doc_in_context": False, "context": []})

        results.append(record)
        mark = "OK" if stage is None else f"{stage.upper()}: {ftype}"
        print(f"[{mark}] {i}. {q[:60]}")
        time.sleep(DELAY)

    out = HERE / f"results-{label}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    summarize(results)
    print(f"Збережено: {out}")
    return 0


def summarize(results):
    total = len(results)
    with_docs = [r for r in results if r["expected_docs"]]
    doc_ok = sum(1 for r in with_docs if r["doc_in_context"])
    correct = sum(1 for r in results if r["failure_stage"] is None)
    search_fail = sum(1 for r in results if r["failure_stage"] == "пошук")
    model_fail = sum(1 for r in results if r["failure_stage"] == "модель")
    errors = sum(1 for r in results if r["failure_stage"] == "помилка")
    answered_wrongly = sum(1 for r in results if not r["expect_answer"] and r.get("found"))
    refused_wrongly = sum(
        1 for r in results
        if r["expect_answer"] and r.get("found") is False and r["failure_stage"] != "помилка"
    )
    warnings = sum(1 for r in results if r.get("warning"))

    usages = [r["usage"] for r in results if r.get("usage")]
    avg_in = sum(u["prompt_tokens"] for u in usages) / len(usages) if usages else 0
    avg_out = sum(u["completion_tokens"] for u in usages) / len(usages) if usages else 0
    ret = [r["elapsed"]["retrieval"] for r in results if r.get("elapsed") and "retrieval" in r["elapsed"]]
    gen = [r["elapsed"]["generation"] for r in results if r.get("elapsed") and "generation" in r["elapsed"]]

    print()
    print(f"Усього питань: {total}")
    print(f"Очікуваний документ у контексті: {doc_ok}/{len(with_docs)}")
    print(f"Без помилок: {correct}/{total}")
    print(f"Помилки пошуку: {search_fail}")
    print(f"Помилки моделі: {model_fail}")
    print(f"Збої API: {errors}")
    print(f"Відповіла там, де мала відмовити: {answered_wrongly}")
    print(f"Відмовила там, де мала відповісти: {refused_wrongly}")
    print(f"Відповідей із попередженням коду: {warnings}")
    print(f"Токени на питання (запит/відповідь): {avg_in:.0f} / {avg_out:.0f}")
    if ret:
        print(f"Середній час пошуку: {sum(ret) / len(ret) * 1000:.0f} мс")
    if gen:
        print(f"Середній час генерації: {sum(gen) / len(gen):.2f} с")


def compare(a: str, b: str) -> int:
    ra = json.loads((HERE / f"results-{a}.json").read_text(encoding="utf-8"))
    rb = json.loads((HERE / f"results-{b}.json").read_text(encoding="utf-8"))
    for x, y in zip(ra, rb):
        if (x["failure_type"], x["found"]) != (y["failure_type"], y["found"]):
            print(f"{x['num']}. {x['question'][:60]}")
            print(f"   {a}: {x['failure_type']} | found={x['found']}")
            print(f"   {b}: {y['failure_type']} | found={y['found']}")
    print()
    print(f"--- {a}")
    summarize(ra)
    print(f"--- {b}")
    summarize(rb)
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "compare":
        sys.exit(compare(sys.argv[2], sys.argv[3]))
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "base"))