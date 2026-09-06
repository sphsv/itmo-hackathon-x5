"""Build the responsive demo; calculations stay in the Python receipt ledger."""
from __future__ import annotations
import json
from pathlib import Path
from sim.ledger import reduce_receipts

def build(root=Path(".")):
    root = Path(root)
    out = root / "proto"
    out.mkdir(parents=True, exist_ok=True)
    goals = [json.loads(line) for line in (root / "ai/out/challenges.jsonl").read_text(encoding="utf-8").splitlines() if line]
    selected = [g for g in goals if g["family_id"] in {"family_ivanovy", "family_dima"}]
    data = {}
    for goal in selected:
        category = goal["categories"][0] if goal["categories"] else "молочка"
        per_unit = (goal["target_saving_minor"] + 1) // 2
        fixture = {"receipt_id": f"demo-{goal['family_id']}-001",
                   "family_id": goal["family_id"], "purchased_on": goal["starts_on"],
                   "items": [{"category": category, "qty": 2, "price_shelf": "300.00",
                              "price_paid": f"{(30000-per_unit)/100:.2f}",
                              "is_markdown": goal["mechanic"] == "markdown_saving"}]}
        data[goal["family_id"]] = {"goal": goal, "state": reduce_receipts(goal, []), "fixture": fixture}
    metrics = json.loads((root / "ai/out/eval.json").read_text())["summary"]
    summary = json.loads((root / "sim/out/summary.json").read_text())
    bundle = {"families": data, "evaluation": metrics, "replay": summary}
    (out / "demo.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    template = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    encoded = json.dumps(bundle, ensure_ascii=False).replace("<", "\\u003c")
    (out / "index.html").write_text(template.replace("__BOOTSTRAP__", encoded), encoding="utf-8")
    return {"prototype": str(out / "index.html"), "interactive_command": "python3 serve_demo.py", "families": list(data)}
