"""Prequential held-out receipt replay, NOT behavioral accuracy or causal uplift."""
from __future__ import annotations
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from .policy import Dataset, recommend_goal, week_start
from sim.exclusions import eligible_category, markdown_allowed
from sim.ledger import normalize_receipt, reduce_receipts

def event_from_row(data, receipt):
    # Source has weeks, not timestamps. Invented day is explicit and stable.
    offset = int(hashlib.sha256(receipt["receipt_id"].encode()).hexdigest()[:8], 16) % 7
    return normalize_receipt({
        "receipt_id": receipt["receipt_id"], "family_id": receipt["family_id"],
        "purchased_on": (week_start(receipt["week"]) + timedelta(days=offset)).isoformat(),
        "items": data.items[receipt["receipt_id"]],
    })

def safety(goal):
    return (all(eligible_category(c) for c in goal["categories"])
            and (goal["mechanic"] != "markdown_saving" or all(markdown_allowed(c) for c in goal["categories"]))
            and (goal["status"] != "assigned" or 0 < goal["target_saving_minor"] <= 15000)
            and goal["reward_points"] == 25)

def evaluate(root=Path(".")):
    root = Path(root)
    data = Dataset(root)
    weeks = data.weeks[8:]
    rows = []
    for fid, profile in sorted(data.profiles.items()):
        if profile["x5_segment"] != "дети до 3":
            continue
        for week in weeks:
            feature = data.features(fid, week)
            for baseline in (False, True):
                goal = recommend_goal(feature, profile, week, consent=True, baseline=baseline)
                future = [event_from_row(data, r) for r in data.by_family[fid] if r["week"] == week]
                state = reduce_receipts(goal, future)
                rows.append({
                    "family_id": fid, "week": week,
                    "system": "static" if baseline else "personalized", "mechanic": goal["mechanic"],
                    "assigned": goal["status"] == "assigned", "safe": safety(goal),
                    "history_grounded": bool(goal["categories"]) and all(
                        feature["category_weeks"].get(c, 0) >= 3 for c in goal["categories"]),
                    "achieved_on_observed_receipts": state["challenge_completed"],
                    "points": state["points"], "growth_cm": state["growth_cm"],
                    "target_saving_minor": goal["target_saving_minor"],
                    "remaining_saving_minor": state["remaining_saving_minor"],
                    "categories": goal["categories"], "feature_cutoff": feature["cutoff_exclusive"],
                })
    systems = {}
    for name in ("personalized", "static"):
        selected = [r for r in rows if r["system"] == name]
        assigned = [r for r in selected if r["assigned"]]
        def rate(key, cohort):
            return round(sum(r[key] for r in cohort) / len(cohort), 4) if cohort else None
        systems[name] = {
            "episodes": len(selected), "assigned": len(assigned),
            "coverage": len(assigned) / len(selected) if selected else None,
            "safety_pass_rate": rate("safe", selected),
            "history_grounded_rate_assigned": rate("history_grounded", assigned),
            "observed_completion_rate_itt": rate("achieved_on_observed_receipts", selected),
            "observed_completion_rate_assigned": rate("achieved_on_observed_receipts", assigned),
            "mean_points_per_episode": round(sum(r["points"] for r in selected) / len(selected), 2) if selected else None,
        }
    summary = {
        "status": "measured_on_synthetic_replay" if rows else "insufficient_history",
        "sample_size": len(rows) // 2, "unique_families": len({r["family_id"] for r in rows}),
        "holdout_weeks": weeks, "history_window_weeks": 8,
        "systems": systems, "constraints_pass_rate": systems["personalized"]["safety_pass_rate"],
        "human_relevance": "not_measured", "human_clarity": "not_measured",
        "business_uplift": "not_measured", "child_stage_used_for_targeting": False,
        "note": "Future receipts unchanged. Completion measures compatibility with synthetic baskets, not behavior change. Temporal replay was inspected during development, not an untouched external test. Days within weeks are synthetic.",
    }
    out = root / "ai" / "out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "eval.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    text = ["# Финальная техническая оценка", "",
            "Временной replay: 8 недель истории → следующая неделя, последние 4 недели. Все данные синтетические.",
            "Заложенный behavior_type не используется моделью и не является целевой метрикой.",
            "Оба подхода видят одинаковые будущие чеки, одинаковые награды и ограничения.",
            "Релевантность, понятность и польза требуют отдельного человеческого review; uplift не измерен.", "",
            f"Семей: {summary['unique_families']}; эпизодов на систему: {summary['sample_size']}.", "",
            "| Система | Назначено | Безопасность | Историческая поддержка | Выполнено на будущих чеках / все эпизоды |",
            "|---|---:|---:|---:|---:|"]
    for name, metrics in systems.items():
        def pct(key):
            return f"{metrics[key]:.1%}" if metrics[key] is not None else "n/a"
        text.append(f"| {name} | {metrics['assigned']} | {pct('safety_pass_rate')} | {pct('history_grounded_rate_assigned')} | {pct('observed_completion_rate_itt')} |")
    text += ["", "Более низкий персональный порог тоже влияет на выполнимость: это не чистое сравнение ранжирования.",
             "Временной replay использовался при разработке и не является нетронутым внешним тестом. Нужны новый holdout и рандомизированный пилот.",
             "Отдельные эпизоды и неуспехи доступны в eval.json; HUMAN_REVIEW.md описывает ручную проверку."]
    (out / "eval.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    return summary
