import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import extraction  # noqa: E402

SAMPLES = ROOT / "samples"
RUNS = Path(__file__).resolve().parent / "runs"
CRITICAL = ("supplier.iban", "supplier.code", "total")
MONEY = {"amount", "price", "quantity", "vat", "total", "total_without_vat"}
ALIASES = {
    "iban_checksum": {"iban_checksum", "iban_format"},
    "missing_required": {"missing_required", "unreadable"},
}
VARIANTS = ["clean", "blur", "lowres", "jpeg", "faded", "photo", "crop", "own"]
OK, WRONG, MISS, FAKE = "правильно", "помилка", "пропуск", "вигадка"
RATE_WAIT = 65
RATE_ATTEMPTS = 4
RETRY_WAIT = {429: RATE_WAIT, 503: 20, 504: 20}


class QuotaExceeded(Exception):
    pass


def load_expected() -> dict:
    data = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    own = SAMPLES / "own" / "expected.json"
    if own.exists():
        data.update(json.loads(own.read_text(encoding="utf-8")))
    return data


def flatten(fields: dict) -> dict:
    out = {}
    for key in ("document_type", "number", "date", "valid_until", "total_without_vat", "vat", "total"):
        out[key] = fields.get(key)
    for side, keys in (("supplier", ("name", "code", "iban")), ("buyer", ("name", "code"))):
        block = fields.get(side) or {}
        for key in keys:
            out[f"{side}.{key}"] = block.get(key)
    for index, item in enumerate(fields.get("items") or []):
        for key in ("name", "unit", "quantity", "price", "amount"):
            out[f"items.{index}.{key}"] = item.get(key)
    return out


def norm(path: str, value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    leaf = path.split(".")[-1]
    if leaf in MONEY:
        try:
            return Decimal(text.replace(" ", "").replace(",", ".")).normalize()
        except InvalidOperation:
            return text
    if leaf in ("name", "unit"):
        return re.sub(r"[\s«»\"'`ʼ’‘]", "", text.lower())
    if leaf in ("iban", "code"):
        return re.sub(r"\s", "", text).upper()
    if leaf == "document_type":
        return text.lower()
    return text


def label(expected, got) -> str:
    if expected is None and got is None:
        return OK
    if expected is None:
        return FAKE
    if got is None:
        return MISS
    return OK if expected == got else WRONG


def compare(expected_fields: dict, document: dict | None) -> dict:
    exp = flatten(expected_fields)
    got = flatten(document or {})
    paths = list(exp) + [p for p in got if p not in exp]
    return {p: label(norm(p, exp.get(p)), norm(p, got.get(p))) for p in paths}


def caught(path: str, issues: list[dict]) -> bool:
    row = ".".join(path.split(".")[:2]) if path.startswith("items.") else None
    for issue in issues:
        if issue["severity"] != "error":
            continue
        field = issue["field"]
        if field == path or field.startswith(path + "."):
            return True
        if row and field.startswith(row + "."):
            return True
        if path in ("total_without_vat", "vat", "total") and issue["rule"].startswith("arithmetic"):
            return True
    return False


def run_one(path: Path):
    content = path.read_bytes()
    for attempt in range(RATE_ATTEMPTS):
        try:
            return extraction.process(content), None
        except extraction.ProcessingError as exc:
            wait = RETRY_WAIT.get(exc.status)
            if wait and attempt < RATE_ATTEMPTS - 1:
                print(f"   {exc.status}, чекаю {wait} с", flush=True)
                time.sleep(wait)
                continue
            if exc.status == 429:
                raise QuotaExceeded(str(exc))
            return None, f"{exc.status}: {exc}"
        except Exception as exc:
            return None, f"{type(exc).__name__}: {exc}"
    return None, "невідома помилка"


def variant_of(key: str, meta: dict) -> str:
    return "own" if key.startswith("own/") else meta.get("variant", "clean")


def row_stats(records: list[dict]) -> dict:
    stats = Counter()
    prompt, total = [], []
    for record in records:
        stats["files"] += 1
        if record.get("decision") is None:
            stats["errors"] += 1
            continue
        if record["decision"] == record["expected_decision"]:
            stats["matched"] += 1
        usage = record.get("usage")
        if usage:
            prompt.append(usage["prompt_tokens"])
            total.append(usage["total_tokens"])
        for path, lab in record["labels"].items():
            stats[lab] += 1
            if lab in (WRONG, FAKE):
                if caught(path, record["issues"]):
                    stats["caught"] += 1
                if record["decision"] == "auto":
                    stats["silent"] += 1
    stats["tokens"] = round(sum(prompt) / len(prompt)) if prompt else 0
    stats["tokens_total"] = round(sum(total) / len(total)) if total else 0
    return stats


def summarize(records: list[dict], tag: str) -> str:
    groups = defaultdict(list)
    for record in records:
        groups[record["variant"]].append(record)

    lines = [f"# Підсумок прогону `{tag}`", ""]
    models = sorted({r["model"] for r in records if r.get("model")})
    if models:
        lines += [f"Модель: {', '.join(models)}", ""]

    lines += [
        "| Варіант | Файлів | Правильно | Помилок | Пропусків | Вигадок | Спіймано правилами | Тихих помилок | Рішення збіглося | Помилок виклику | Токени запиту | Токени всього |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for variant in VARIANTS:
        if variant not in groups:
            continue
        s = row_stats(groups[variant])
        lines.append(
            f"| {variant} | {s['files']} | {s[OK]} | {s[WRONG]} | {s[MISS]} | {s[FAKE]} | {s['caught']} | "
            f"{s['silent']} | {s['matched']}/{s['files']} | {s['errors']} | {s['tokens']} | {s['tokens_total']} |"
        )
    total = row_stats(records)
    lines.append(
        f"| **разом** | {total['files']} | {total[OK]} | {total[WRONG]} | {total[MISS]} | {total[FAKE]} | "
        f"{total['caught']} | {total['silent']} | {total['matched']}/{total['files']} | {total['errors']} | "
        f"{total['tokens']} | {total['tokens_total']} |"
    )

    lines += ["", "## Критичні поля (IBAN, код постачальника, до сплати)", ""]
    lines += ["| Варіант | Правильно | Помилок | Пропусків | Вигадок |", "|---|---|---|---|---|"]
    for variant in VARIANTS:
        if variant not in groups:
            continue
        counter = Counter()
        for record in groups[variant]:
            labels = record.get("labels") or {}
            for path in CRITICAL:
                if path in labels:
                    counter[labels[path]] += 1
        lines.append(f"| {variant} | {counter[OK]} | {counter[WRONG]} | {counter[MISS]} | {counter[FAKE]} |")

    lines += ["", "## Матриця рішень (очікувалось → отримано)", ""]
    matrix = Counter((r["expected_decision"], r.get("decision") or "помилка") for r in records)
    lines += ["| Очікувалось | auto | review | reject | помилка |", "|---|---|---|---|---|"]
    for expected in ("auto", "review", "reject"):
        lines.append(
            f"| {expected} | " + " | ".join(str(matrix[(expected, got)]) for got in ("auto", "review", "reject", "помилка")) + " |"
        )

    stage = defaultdict(list)
    for record in records:
        for name, value in (record.get("elapsed") or {}).items():
            stage[name].append(value)
    lines += ["", "## Середній час за етапами, с", ""]
    for name, values in stage.items():
        lines.append(f"- {name}: {sum(values) / len(values):.3f}")

    lines += ["", "## По файлах", ""]
    lines += ["| Файл | Очікувалось | Отримано | Правила (error) | Не спрацювали, але мали | Неправильні поля |", "|---|---|---|---|---|---|"]
    for record in records:
        if record.get("decision") is None:
            lines.append(f"| {record['file']} | {record['expected_decision']} | ПОМИЛКА | {record.get('error')} | | |")
            continue
        fired = {i["rule"] for i in record["issues"] if i["severity"] == "error"}
        missing = [m for m in record["expected_checks"] if not (ALIASES.get(m, {m}) & fired)]
        bad = [f"{p}:{l}" for p, l in record["labels"].items() if l != OK]
        lines.append(
            f"| {record['file']} | {record['expected_decision']} | {record['decision']} | "
            f"{', '.join(sorted(fired)) or '—'} | {', '.join(missing) or '—'} | {'; '.join(bad) or '—'} |"
        )
    return "\n".join(lines)


def save(records: list[dict], out_dir: Path, tag: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "summary.md").write_text(summarize(records, tag), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--only", default="")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    expected = load_expected()
    out_dir = RUNS / args.tag
    done = {}
    results_path = out_dir / "results.json"
    if args.resume and results_path.exists():
        for record in json.loads(results_path.read_text(encoding="utf-8")):
            if record.get("decision") is not None:
                done[record["file"]] = record

    records = []
    stopped = False
    for key in sorted(expected):
        if args.only and args.only not in key:
            continue
        if key in done:
            records.append(done[key])
            continue
        path = SAMPLES / key
        if not path.exists():
            print(f"пропущено, немає файлу: {key}")
            continue
        if stopped:
            continue
        meta = expected[key]
        print(f"→ {key}", flush=True)
        try:
            result, error = run_one(path)
        except QuotaExceeded as exc:
            print(f"\nЛіміт ключа вичерпано ({exc}). Результати збережено, продовжіть пізніше з --resume.")
            stopped = True
            continue
        if error:
            print(f"   помилка: {error}", flush=True)
        record = {
            "file": key,
            "variant": variant_of(key, meta),
            "expected_decision": meta["expected_decision"],
            "expected_checks": meta.get("expected_checks", []),
            "error": error,
            "decision": None,
        }
        if result:
            record.update(
                model=result.model,
                decision=result.decision,
                reasons=result.reasons,
                issues=[asdict(i) for i in result.issues],
                labels=compare(meta["fields"], result.document),
                usage=result.usage,
                elapsed=result.elapsed,
                image=result.image,
                document=result.document,
                raw=result.raw,
            )
        records.append(record)
        save(records, out_dir, args.tag)
        if args.sleep:
            time.sleep(args.sleep)

    save(records, out_dir, args.tag)
    print()
    print((out_dir / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()