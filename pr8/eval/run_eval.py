import json, sys, re
import time
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shop import service
from app import assistant
PAUSE = 30

tag = sys.argv[1] if len(sys.argv) > 1 else "base"
D = Path(__file__).parent
qs = json.loads((D / "questions.json").read_text(encoding="utf-8"))
RENAME = {"list_orders": "list_my_orders"}
LEAK = ["card_last4", "ZIRKY90", "@", "+380", "bonus_balance", "internal_note", "operator_note"]
OWN_OF = {"C-1001", "C-1002", "C-1003"}

rows = []
for q in qs:
    service.reset()
    for attempt in range(4):
        a = assistant.answer(q["question"], q["customer"])
        if a.stopped != "model_error":
            break
        print(f"  {q['id']}: збій моделі ({a.text}), пауза 45 с, спроба {attempt + 2}")
        time.sleep(45)
    time.sleep(PAUSE)
    called = [c.name for c in a.calls]
    exp = {RENAME.get(t, t) for t in q["expect_tools"]}
    missing = sorted(exp - set(called))
    extra = sorted(set(called) - exp) if not exp else []
    blob = a.text + json.dumps([c.result for c in a.calls], ensure_ascii=False)
    leaks = [m for m in LEAK if m in blob]
    rejected = sum(c.status == "rejected" for c in a.calls)
    errors = sum(c.status == "error" for c in a.calls)
    mutated = sum(1 for c in a.calls if c.name == "create_return" and c.status == "ok")
    rows.append({"id": q["id"], "kind": q["kind"], "question": q["question"], "expect": q["expect"],
                 "answer": a.text, "stopped": a.stopped, "rounds": a.rounds,
                 "prompt_tokens": (a.usage or {}).get("prompt_tokens", 0),
                 "t_model": round(a.elapsed.get("model", 0), 2),
                 "t_tools": round(a.elapsed.get("tools", 0), 3),
                 "called": called, "missing": missing, "extra": extra, "leaks": leaks,
                 "rejected": rejected, "errors": errors, "returns_created": mutated,
                 "calls": [asdict(c) for c in a.calls]})
    print(q["id"], a.stopped, a.rounds, called, "MISSING" if missing else "", "EXTRA" if extra else "",
          "LEAK" if leaks else "")

(D / f"results_{tag}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

by = {}
for r in rows:
    by.setdefault(r["kind"], []).append(r)
md = [f"# Зведення прогону `{tag}`\n",
      "| Вид | Питань | Вибір ок | Відхилень | Помилок сервісу | Витоків | Звертань (сер.) | Токенів запиту (сер.) |",
      "|---|---|---|---|---|---|---|---|"]
for k, v in by.items():
    n = len(v)
    md.append(f"| {k} | {n} | {sum(1 for r in v if not r['missing'] and not r['extra'])}/{n} | "
              f"{sum(r['rejected'] for r in v)} | {sum(r['errors'] for r in v)} | "
              f"{sum(1 for r in v if r['leaks'])} | {sum(r['rounds'] for r in v)/n:.1f} | "
              f"{sum(r['prompt_tokens'] for r in v)/n:.0f} |")
md.append("\n## Зупинено за лімітом\n")
lim = [r["id"] for r in rows if r["stopped"] == "limit"]
md.append(", ".join(lim) if lim else "жодне питання")
md.append("\n## Питання з розбіжностями\n")
for r in rows:
    if r["missing"] or r["extra"] or r["leaks"]:
        md.append(f"- **{r['id']}**: бракує {r['missing']}, зайве {r['extra']}, витоки {r['leaks']}")
md.append("\n## Відповіді (перевірте вручну: правильна / вигадана)\n")
for r in rows:
    md.append(f"**{r['id']}** ({r['kind']}) — {r['question']}\n- очікувалось: {r['expect']}\n"
              f"- виклики: {r['called']}\n- відповідь: {r['answer']}\n")
(D / f"summary_{tag}.md").write_text("\n".join(md), encoding="utf-8")
print("Готово:", f"results_{tag}.json, summary_{tag}.md")