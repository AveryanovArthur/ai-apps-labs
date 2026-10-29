import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import load_expected, flatten, norm, WRONG

FOLD = str.maketrans("ABCEHIKMOPTXaceiopxy", "АВСЕНІКМОРТХасеіорху")
fold = lambda s: s.translate(FOLD) if isinstance(s, str) else s

records = json.loads((Path(__file__).parent / "runs" / sys.argv[1] / "results.json").read_text(encoding="utf-8"))
expected = load_expected()
total = homo = 0
for r in records:
    if r.get("decision") is None:
        continue
    exp, got = flatten(expected[r["file"]]["fields"]), flatten(r["document"])
    for path, lab in r["labels"].items():
        if lab != WRONG:
            continue
        total += 1
        e, g = norm(path, exp.get(path)), norm(path, got.get(path))
        if isinstance(e, str) and isinstance(g, str) and fold(e) == fold(g):
            homo += 1
            print(r["file"], path, repr(e), "->", repr(g))
print(f"помилок: {total}, з них гомогліфів: {homo}")