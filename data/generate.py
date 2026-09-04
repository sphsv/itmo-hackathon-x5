from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path


SEGMENTS = ["молодёжь", "вредные привычки", "дети до 3", "зрелые", "старшие"]
NETWORK_WEIGHTS = {"ТС5": 0.70, "ТСХ": 0.10, "ТСЧ": 0.20}
SEGMENT_WEIGHTS = {
    "ТС5": [0.37, 0.05, 0.26, 0.21, 0.11],
    "ТСХ": [0.31, 0.03, 0.26, 0.32, 0.09],
    "ТСЧ": [0.27, 0.04, 0.28, 0.24, 0.18],
}
AVG_CHECK = {"ТС5": 564.0, "ТСХ": 878.0, "ТСЧ": 711.0}
CHILD_STAGES = ["0-6", "6-9", "9-12", "1-2", "2-3"]
BEHAVIOURS = ["хозяин", "охотник", "категорийный"]
SAFE_MARKDOWN = {"молочка", "хлеб", "овощи", "фрукты", "готовая еда", "выпечка"}
EXCLUDED = {"заменители грудного молока", "алкоголь", "табак"}
BABY_FOOD = {"детское пюре", "детские каши", "детские творожки", "заменители грудного молока"}
CATEGORIES = [
    "молочка", "кефир/йогурты", "творог", "хлеб", "овощи", "фрукты", "мясо",
    "курица", "рыба", "крупы", "макароны", "консервы", "готовая еда", "выпечка",
    "снеки", "напитки", "кофе/чай", "сладкое", "замороженное", "бытовая химия",
    "гигиена", "подгузники", "детское пюре", "детские каши", "детские творожки",
    "заменители грудного молока", "детская гигиена", "алкоголь", "табак",
]


def _weighted_choice(rng: random.Random, options: list[str], weights: list[float]) -> str:
    return rng.choices(options, weights=weights, k=1)[0]


def _top_categories(rng: random.Random, segment: str) -> list[str]:
    base = ["молочка", "хлеб", "овощи", "фрукты", "мясо", "крупы", "гигиена"]
    if segment == "дети до 3":
        base = ["подгузники", "детская гигиена", "молочка", "детские каши", "фрукты", "хлеб"]
    elif segment == "молодёжь":
        base = ["готовая еда", "снеки", "напитки", "выпечка", "молочка", "фрукты"]
    elif segment == "старшие":
        base = ["молочка", "крупы", "овощи", "хлеб", "творог", "рыба"]
    return rng.sample(base, k=5)


def _profile(rng: random.Random, index: int) -> dict[str, object]:
    network = _weighted_choice(rng, list(NETWORK_WEIGHTS), list(NETWORK_WEIGHTS.values()))
    segment = _weighted_choice(rng, SEGMENTS, SEGMENT_WEIGHTS[network])
    behaviour_weights = [0.50, 0.30, 0.20] if segment == "дети до 3" else [0.60, 0.30, 0.10]
    behaviour = _weighted_choice(rng, BEHAVIOURS, behaviour_weights)
    child_stage = rng.choice(CHILD_STAGES) if segment == "дети до 3" else "none"
    freq_ranges = {
        "дети до 3": (1.5, 3.0), "молодёжь": (0.5, 1.5), "зрелые": (1.0, 2.0),
        "старшие": (2.0, 4.0), "вредные привычки": (0.8, 1.8),
    }
    low, high = freq_ranges[segment]
    promo, markdown = {
        "хозяин": (0.30, 0.05), "охотник": (0.50, 0.25), "категорийный": (0.30, 0.05)
    }[behaviour]
    avg_check = AVG_CHECK[network] * (1.20 if segment == "дети до 3" else 1.0)
    return {
        "user_id": f"u_{index:06d}",
        "family_id": f"family_{index:06d}",
        "network_home": network,
        "x5_segment": segment,
        "is_app_user": "true",
        "behavior_type": behaviour,
        "child_stage": child_stage,
        "city_bucket": rng.randint(1, 20),
        "base_freq_per_week": round(rng.uniform(low, high), 2),
        "avg_check_rub": round(avg_check, 2),
        "promo_share": promo,
        "markdown_share": markdown,
        "top_categories": ";".join(_top_categories(rng, segment)),
    }


def _demo_profiles() -> list[dict[str, object]]:
    return [
        {
            "user_id": "u_ivanovy", "family_id": "family_ivanovy", "network_home": "ТС5",
            "x5_segment": "дети до 3", "is_app_user": "true", "behavior_type": "хозяин",
            "child_stage": "6-9", "city_bucket": 7, "base_freq_per_week": 2.4,
            "avg_check_rub": 676.8, "promo_share": 0.30, "markdown_share": 0.05,
            "top_categories": "подгузники;детская гигиена;молочка;фрукты;хлеб",
        },
        {
            "user_id": "u_dima", "family_id": "family_dima", "network_home": "ТСЧ",
            "x5_segment": "дети до 3", "is_app_user": "true", "behavior_type": "охотник",
            "child_stage": "2-3", "city_bucket": 12, "base_freq_per_week": 2.1,
            "avg_check_rub": 853.2, "promo_share": 0.50, "markdown_share": 0.25,
            "top_categories": "молочка;хлеб;фрукты;подгузники;готовая еда",
        },
    ]


def _visits(rng: random.Random, rate: float) -> int:
    base = int(rate)
    visits = base + int(rng.random() < rate - base)
    if rng.random() < 0.08:
        visits += 1
    if rng.random() < 0.05:
        visits = max(0, visits - 1)
    return visits


def generate(
    n_families: int = 500,
    seed: int = 42,
    history_weeks: int = 12,
    root: Path | str = Path("."),
) -> dict[str, object]:
    if n_families < 3:
        raise ValueError("n_families must be at least 3")
    root = Path(root)
    out_dir = root / "data" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    profiles = _demo_profiles() + [_profile(rng, i) for i in range(2, n_families)]

    profile_fields = list(profiles[0])
    with (out_dir / "profiles.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=profile_fields)
        writer.writeheader()
        writer.writerows(profiles)

    receipt_fields = [
        "receipt_id", "family_id", "user_id", "week", "network_home",
        "check_total_rub", "savings_rub", "items_count",
    ]
    item_fields = [
        "receipt_id", "sku", "category", "qty", "price_shelf", "price_paid",
        "is_promo", "is_markdown", "is_excluded",
    ]
    weeks = [f"2026-W{37 - history_weeks + i:02d}" for i in range(history_weeks)]
    receipt_count = 0
    item_count = 0
    with (
        (out_dir / "receipts.csv").open("w", encoding="utf-8", newline="") as receipts_fh,
        (out_dir / "receipt_items.csv").open("w", encoding="utf-8", newline="") as items_fh,
    ):
        receipts_writer = csv.DictWriter(receipts_fh, fieldnames=receipt_fields)
        items_writer = csv.DictWriter(items_fh, fieldnames=item_fields)
        receipts_writer.writeheader()
        items_writer.writeheader()
        for profile in profiles:
            top = str(profile["top_categories"]).split(";")
            for week in weeks:
                for _ in range(_visits(rng, float(profile["base_freq_per_week"]))):
                    receipt_count += 1
                    receipt_id = f"r_{receipt_count:08d}"
                    n_items = rng.randint(5, 11)
                    target = max(180.0, rng.gauss(float(profile["avg_check_rub"]), float(profile["avg_check_rub"]) * 0.18))
                    raw = [rng.uniform(0.55, 1.45) for _ in range(n_items)]
                    raw_sum = sum(raw)
                    paid_total = 0.0
                    shelf_total = 0.0
                    rows = []
                    for item_no, weight in enumerate(raw):
                        if profile["behavior_type"] == "категорийный" and rng.random() < 0.45:
                            category = top[0]
                        else:
                            category = rng.choice(top) if rng.random() < 0.72 else rng.choice(CATEGORIES)
                        shelf = target * weight / raw_sum
                        promo = rng.random() < float(profile["promo_share"])
                        markdown = (
                            category in SAFE_MARKDOWN
                            and category not in BABY_FOOD
                            and rng.random() < float(profile["markdown_share"])
                        )
                        discount = rng.uniform(0.30, 0.50) if markdown else (rng.uniform(0.08, 0.22) if promo else 0.0)
                        paid = shelf * (1 - discount)
                        shelf_total += shelf
                        paid_total += paid
                        rows.append({
                            "receipt_id": receipt_id,
                            "sku": f"sku_{CATEGORIES.index(category):02d}_{item_no:02d}",
                            "category": category,
                            "qty": 1,
                            "price_shelf": f"{shelf:.2f}",
                            "price_paid": f"{paid:.2f}",
                            "is_promo": str(promo).lower(),
                            "is_markdown": str(markdown).lower(),
                            "is_excluded": str(category in EXCLUDED).lower(),
                        })
                    items_writer.writerows(rows)
                    item_count += len(rows)
                    receipts_writer.writerow({
                        "receipt_id": receipt_id,
                        "family_id": profile["family_id"],
                        "user_id": profile["user_id"],
                        "week": week,
                        "network_home": profile["network_home"],
                        "check_total_rub": f"{paid_total:.2f}",
                        "savings_rub": f"{shelf_total - paid_total:.2f}",
                        "items_count": len(rows),
                    })

    segment_counts = Counter(str(p["x5_segment"]) for p in profiles)
    return {
        "families": len(profiles),
        "receipts": receipt_count,
        "items": item_count,
        "weeks": history_weeks,
        "segment_share": {k: round(v / len(profiles), 3) for k, v in sorted(segment_counts.items())},
        "seed": seed,
    }


if __name__ == "__main__":
    print(generate())
