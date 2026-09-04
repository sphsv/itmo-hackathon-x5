from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from data.generate import BABY_FOOD, EXCLUDED


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def build_features(root: Path | str = Path(".")) -> tuple[list[dict[str, object]], dict[str, dict[str, str]]]:
    root = Path(root)
    profiles = _read_csv(root / "data" / "out" / "profiles.csv")
    receipts = _read_csv(root / "data" / "out" / "receipts.csv")
    items = _read_csv(root / "data" / "out" / "receipt_items.csv")
    profile_by_family = {p["family_id"]: p for p in profiles}
    receipt_family = {r["receipt_id"]: r["family_id"] for r in receipts}
    receipt_week = {r["receipt_id"]: r["week"] for r in receipts}
    recent_weeks = sorted({r["week"] for r in receipts})[-8:]

    category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    totals: Counter[str] = Counter()
    markdowns: Counter[str] = Counter()
    promos: Counter[str] = Counter()
    savings: defaultdict[str, float] = defaultdict(float)
    visits: Counter[str] = Counter()
    for receipt in receipts:
        if receipt["week"] in recent_weeks:
            family_id = receipt["family_id"]
            visits[family_id] += 1
            savings[family_id] += float(receipt["savings_rub"])
    for item in items:
        if receipt_week.get(item["receipt_id"]) not in recent_weeks:
            continue
        family_id = receipt_family[item["receipt_id"]]
        totals[family_id] += 1
        category_counts[family_id][item["category"]] += 1
        markdowns[family_id] += item["is_markdown"] == "true"
        promos[family_id] += item["is_promo"] == "true"

    features: list[dict[str, object]] = []
    for family_id, profile in profile_by_family.items():
        total = max(totals[family_id], 1)
        top = category_counts[family_id].most_common(5)
        top_share = top[0][1] / total if top else 0.0
        markdown_rate = markdowns[family_id] / total
        promo_rate = promos[family_id] / total
        if top_share >= 0.27:
            inferred = "категорийный"
        elif markdown_rate >= 0.07:
            inferred = "охотник"
        else:
            inferred = "хозяин"
        features.append({
            "family_id": family_id,
            "user_id": profile["user_id"],
            "visits_8w": visits[family_id],
            "items_8w": totals[family_id],
            "markdown_rate": round(markdown_rate, 4),
            "promo_rate": round(promo_rate, 4),
            "top_category_share": round(top_share, 4),
            "top_categories": [name for name, _ in top],
            "savings_8w": round(savings[family_id], 2),
            "inferred_behavior": inferred,
        })
    return features, profile_by_family


def _ideal_mechanic(behaviour: str, child_stage: str) -> str:
    if behaviour == "охотник":
        return "save_product"
    if behaviour == "категорийный" and child_stage in {"1-2", "2-3"}:
        return "stage_mission"
    return "rostomer"


def recommend(feature: dict[str, object], profile: dict[str, str]) -> dict[str, object]:
    inferred = str(feature["inferred_behavior"])
    mechanic = _ideal_mechanic(inferred, profile["child_stage"])
    safe_categories = [
        category for category in feature["top_categories"]
        if category not in EXCLUDED and category not in BABY_FOOD
    ][:2] or ["молочка", "хлеб"]
    explanations = {
        "хозяин": "Вы регулярно собираете семейную корзину — покажем накопленный прогресс.",
        "охотник": "В ваших чеках заметна уценка — сначала покажем доступные товары «Спаси продукт».",
        "категорийный": "Покупки сосредоточены в нескольких категориях — предложим короткую цель по привычной корзине.",
    }
    product_explanations = {
        "хозяин": "Низкая концентрация и умеренная доля промо: основной экран — ростомер.",
        "охотник": "Высокая доля markdown: основной экран — уценка.",
        "категорийный": "Высокая концентрация категории: основной экран — тематическая цель.",
    }
    target = max(80, min(300, round(float(feature["savings_8w"]) / 8 / 10) * 10))
    stage_mission = None
    if mechanic == "stage_mission":
        stage_mission = {
            "name": "Самостоятельный шаг",
            "items": ["детская гигиена"],
            "stage": profile["child_stage"],
        }
    habitual = [
        {"category": category, "expected_saving_rub": max(20, target // len(safe_categories)),
         "why": "входит в частые категории семьи"}
        for category in safe_categories
    ]
    return {
        "user_id": profile["user_id"],
        "family_id": profile["family_id"],
        "behavior_type": inferred,
        "type_evidence": (
            f"markdown={float(feature['markdown_rate']):.1%}, "
            f"концентрация топ-категории={float(feature['top_category_share']):.1%}"
        ),
        "mechanic_first": mechanic,
        "mechanic_explanation_user": explanations[inferred],
        "mechanic_explanation_product": product_explanations[inferred],
        "challenge": {
            "week": "2026-W37",
            "habitual_items": habitual,
            "stage_mission": stage_mission,
            "markdown_categories": [c for c in safe_categories if c in {"молочка", "хлеб", "овощи", "фрукты", "готовая еда"}],
            "target_saving_rub": target,
        },
        "constraints_checked": {
            "no_excluded": not any(c in EXCLUDED for c in safe_categories),
            "no_baby_food_markdown": not any(c in BABY_FOOD for c in safe_categories),
            "stage_matches": stage_mission is None or stage_mission["stage"] == profile["child_stage"],
        },
    }


def _sample(features: list[dict[str, object]], profiles: dict[str, dict[str, str]], size: int, seed: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    chosen: list[dict[str, object]] = []
    by_type: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for feature in features:
        by_type[profiles[str(feature["family_id"])]["behavior_type"]].append(feature)
    demo_ids = {"family_ivanovy", "family_dima"}
    chosen.extend([f for f in features if f["family_id"] in demo_ids])
    per_type = max(1, size // 3)
    for behaviour in ["хозяин", "охотник", "категорийный"]:
        candidates = [f for f in by_type[behaviour] if f["family_id"] not in demo_ids]
        rng.shuffle(candidates)
        chosen.extend(candidates[:per_type])
    seen = set()
    unique = []
    for feature in chosen:
        if feature["family_id"] not in seen:
            seen.add(feature["family_id"])
            unique.append(feature)
    if len(unique) < size:
        rest = [f for f in features if f["family_id"] not in seen]
        rng.shuffle(rest)
        unique.extend(rest[: size - len(unique)])
    return unique[:size]


def run_agent(sample_size: int = 30, seed: int = 42, root: Path | str = Path(".")) -> dict[str, object]:
    root = Path(root)
    out_dir = root / "ai" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    features, profiles = build_features(root)
    sampled = _sample(features, profiles, min(sample_size, len(features)), seed)
    recommendations = [recommend(f, profiles[str(f["family_id"])]) for f in sampled]
    with (out_dir / "challenges.jsonl").open("w", encoding="utf-8") as fh:
        for row in recommendations:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    feature_fields = [
        "family_id", "user_id", "visits_8w", "items_8w", "markdown_rate",
        "promo_rate", "top_category_share", "savings_8w", "inferred_behavior",
    ]
    with (out_dir / "features.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=feature_fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in feature_fields} for row in features)
    counts = Counter(r["mechanic_first"] for r in recommendations)
    return {"sample": len(recommendations), "mechanics": dict(sorted(counts.items()))}
