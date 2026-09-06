"""Generate final assignments for the entire eligible target cohort."""
from __future__ import annotations
import csv
import json
from collections import Counter
from pathlib import Path
from .policy import Dataset, next_week, recommend_goal

def build_features(root=Path(".")):
    data = Dataset(Path(root))
    cutoff = next_week(data.weeks[-1])
    features = [data.features(fid, cutoff) for fid in sorted(data.profiles)
                if data.profiles[fid]["x5_segment"] == "дети до 3"]
    return features, data.profiles

def run_agent(sample_size=40, seed=42, root=Path(".")):
    root = Path(root)
    out = root / "ai" / "out"
    out.mkdir(parents=True, exist_ok=True)
    features, profiles = build_features(root)
    recommendations = [recommend_goal(f, profiles[f["family_id"]], f["cutoff_exclusive"], consent=True)
                       for f in features]
    (out / "challenges.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                                  for r in recommendations), encoding="utf-8")
    (out / "features.json").write_text(json.dumps(features, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "features.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["family_id", "cutoff_exclusive", "visits", "history_start"])
        writer.writeheader()
        writer.writerows({k: f[k] for k in writer.fieldnames} for f in features)
    return {"sample": len(recommendations), "scope": "all_target_profiles",
            "assigned": sum(r["status"] == "assigned" for r in recommendations),
            "deferred": sum(r["status"] == "deferred" for r in recommendations),
            "mechanics": dict(Counter(r["mechanic"] for r in recommendations if r["status"] == "assigned")),
            "synthetic_consent": True, "seed": seed}
