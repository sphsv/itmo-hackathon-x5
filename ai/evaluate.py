from __future__ import annotations

import csv
import json
from pathlib import Path

from data.generate import BABY_FOOD, EXCLUDED
from .personalizer import _ideal_mechanic


def evaluate(root: Path | str = Path(".")) -> dict[str, object]:
    root = Path(root)
    out_dir = root / "ai" / "out"
    with (root / "data" / "out" / "profiles.csv").open(encoding="utf-8", newline="") as fh:
        profiles = {row["user_id"]: row for row in csv.DictReader(fh)}
    recommendations = [
        json.loads(line)
        for line in (out_dir / "challenges.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = []
    for rec in recommendations:
        profile = profiles[rec["user_id"]]
        ideal = _ideal_mechanic(profile["behavior_type"], profile["child_stage"])
        categories = [item["category"] for item in rec["challenge"]["habitual_items"]]
        safe = not any(c in EXCLUDED or c in BABY_FOOD for c in categories)
        constraints = all(rec["constraints_checked"].values()) and safe
        mechanic_hit = rec["mechanic_first"] == ideal
        type_hit = rec["behavior_type"] == profile["behavior_type"]
        hit = type_hit and constraints
        baseline_hit = profile["behavior_type"] == "хозяин"
        rows.append({
            "user_id": rec["user_id"],
            "true_type": profile["behavior_type"],
            "predicted_type": rec["behavior_type"],
            "ideal_mechanic": ideal,
            "recommended": rec["mechanic_first"],
            "constraints_ok": constraints,
            "type_hit": type_hit,
            "hit": hit,
            "static_baseline_hit": baseline_hit,
        })
    n = max(len(rows), 1)
    hit_rate = sum(r["hit"] for r in rows) / n
    baseline_rate = sum(r["static_baseline_hit"] for r in rows) / n
    result = {
        "sample_size": len(rows),
        "personalized_behavior_accuracy": round(hit_rate, 4),
        "static_one_size_fits_all_accuracy": round(baseline_rate, 4),
        "absolute_uplift_pp": round((hit_rate - baseline_rate) * 100, 1),
        "constraints_pass_rate": round(sum(r["constraints_ok"] for r in rows) / n, 4),
        "note": "Синтетический offline-eval; не доказывает продуктовый uplift.",
    }
    (out_dir / "eval.json").write_text(json.dumps({"summary": result, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Offline eval персонализатора", "",
        "> Синтетическая выборка. Метрика проверяет техническое соответствие известному сценарию, а не продуктовый uplift.", "",
        f"- Размер выборки: **{len(rows)}**",
        f"- Personalized behavior accuracy: **{hit_rate:.1%}**",
        f"- One-size-fits-all baseline accuracy: **{baseline_rate:.1%}**",
        f"- Разница: **{(hit_rate - baseline_rate) * 100:.1f} п.п.**",
        f"- Constraints pass rate: **{result['constraints_pass_rate']:.1%}**", "",
        "| user_id | true | predicted | recommended | hit |",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {r['user_id']} | {r['true_type']} | {r['predicted_type']} | {r['recommended']} | {'yes' if r['hit'] else 'no'} |"
        for r in rows
    )
    (out_dir / "eval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
