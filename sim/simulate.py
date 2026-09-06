"""Replay existing synthetic receipts through the final goal rules; no uplift RNG."""
from __future__ import annotations
import csv
import json
from collections import Counter
from pathlib import Path
from ai.policy import Dataset, recommend_goal, variant
from ai.evaluate import event_from_row
from .ledger import reduce_receipts

def league_table(profiles, scores):
    # Small target-only cohorts; equal scores receive the same competition rank.
    groups = {}
    for profile in sorted(profiles, key=lambda p: p["family_id"]):
        groups.setdefault(profile["network_home"], []).append(profile)
    rows = []
    for network, group in groups.items():
        for start in range(0, len(group), 50):
            chunk = group[start:start + 50]
            ordered = sorted(chunk, key=lambda p: (-scores[p["family_id"]], p["family_id"]))
            cutoff = scores[ordered[min(2, len(ordered)-1)]["family_id"]]
            for p in ordered:
                score = scores[p["family_id"]]
                rank = 1 + sum(scores[q["family_id"]] > score for q in ordered)
                rows.append({"family_id": p["family_id"], "league_id": f"{network}-{start//50+1}",
                             "members": len(ordered), "rank": rank, "points": score,
                             "gap_to_top3_points": max(0, cutoff-score)})
    return rows

def simulate(weeks=4, seed=42, root=Path(".")):
    if not 1 <= weeks <= 4:
        raise ValueError("Final replay supports 1..4 held-out weeks after 8 history weeks")
    root = Path(root)
    data = Dataset(root)
    selected = data.weeks[8:][-weeks:]
    profiles = [p for p in data.profiles.values() if p["x5_segment"] == "дети до 3"]
    rows, scores, height = [], Counter(), Counter()
    for p in sorted(profiles, key=lambda p: p["family_id"]):
        fid = p["family_id"]
        for week in selected:
            goal = recommend_goal(data.features(fid, week), p, week, consent=True)
            receipts = [event_from_row(data, r) for r in data.by_family[fid] if r["week"] == week]
            state = reduce_receipts(goal, receipts)
            scores[fid] += state["points"]
            height[fid] += round(state["growth_cm"] * 10)
            rows.append({"family_id": fid, "week": week, "assigned": goal["status"] == "assigned",
                         "challenge_completed": state["challenge_completed"],
                         "goal_saving_minor": state["totals"]["goal_saving_minor"],
                         "eligible_saving_minor": state["totals"]["eligible_saving_minor"],
                         "growth_delta_cm": state["growth_cm"], "growth_total_cm": height[fid]/10,
                         "points": state["points"], "purchase_days_synthetic": state["purchase_days"]})
    league = league_table(profiles, scores)
    out = root / "sim" / "out"
    out.mkdir(parents=True, exist_ok=True)
    for filename, table in (("heights.csv", rows), ("leagues.csv", league)):
        with (out / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(table[0]) if table else ["family_id"])
            writer.writeheader()
            writer.writerows(table)
    summary = {
        "families": len(profiles), "weeks": len(selected), "episodes": len(rows),
        "completed": sum(r["challenge_completed"] for r in rows),
        "points": sum(scores.values()),
        "demos": {p["family_id"]: {"growth_cm": height[p["family_id"]]/10, **next(
            row for row in league if row["family_id"] == p["family_id"])}
            for p in profiles if p["family_id"] in {"family_ivanovy", "family_dima"}},
        "pilot_assignment_preview": dict(Counter(variant(p["family_id"]) for p in profiles)),
        "pilot_effect": "not_measured",
        "league_status": "offline_optional_preview_not_live_competition",
        "referral_status": "future_not_implemented",
        "note": "Target cohort only; no extra purchases generated. Dates inside source weeks are synthetic. C/D sharing effects are not simulated.",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
