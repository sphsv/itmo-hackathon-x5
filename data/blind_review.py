from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


RATING_FIELDS = [
    "review_id",
    "assessor_id",
    "option_a_relevance_1_5",
    "option_a_feasibility_1_5",
    "option_a_clarity_1_5",
    "option_a_usefulness_1_5",
    "option_a_safety_1_5",
    "option_b_relevance_1_5",
    "option_b_feasibility_1_5",
    "option_b_clarity_1_5",
    "option_b_usefulness_1_5",
    "option_b_safety_1_5",
    "preferred_option",
    "comment",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _stratified_sample(
    profiles: list[dict[str, str]], sample_size: int, seed: int
) -> list[dict[str, str]]:
    groups: defaultdict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for profile in profiles:
        groups[(profile["child_stage"], profile["behavior_type"])].append(profile)

    rng = random.Random(seed)
    for group in groups.values():
        group.sort(key=lambda row: row["family_id"])
        rng.shuffle(group)

    selected: list[dict[str, str]] = []
    ordered_keys = sorted(groups)
    while len(selected) < min(sample_size, len(profiles)):
        added = False
        for key in ordered_keys:
            if groups[key] and len(selected) < sample_size:
                selected.append(groups[key].pop())
                added = True
        if not added:
            break
    rng.shuffle(selected)
    return selected


def prepare_blind_review_sample(
    sample_size: int = 40,
    seed: int = 42,
    weeks: int = 8,
    root: Path | str = Path("."),
) -> dict[str, object]:
    if sample_size < 1:
        raise ValueError("sample_size must be positive")
    if weeks < 1:
        raise ValueError("weeks must be positive")

    root = Path(root)
    out_dir = root / "data" / "out"
    profiles = _read_csv(out_dir / "target_profiles.csv")
    receipts = _read_csv(out_dir / "target_receipts.csv")
    items = _read_csv(out_dir / "target_receipt_items.csv")
    selected = _stratified_sample(profiles, sample_size, seed)
    selected_family_ids = {row["family_id"] for row in selected}

    recent_weeks = sorted({row["week"] for row in receipts})[-weeks:]
    selected_receipts = [
        row
        for row in receipts
        if row["family_id"] in selected_family_ids and row["week"] in recent_weeks
    ]
    receipt_family = {row["receipt_id"]: row["family_id"] for row in selected_receipts}
    visits: Counter[str] = Counter()
    savings: defaultdict[str, float] = defaultdict(float)
    spend: defaultdict[str, float] = defaultdict(float)
    category_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    item_counts: Counter[str] = Counter()
    promo_counts: Counter[str] = Counter()
    markdown_counts: Counter[str] = Counter()

    for receipt in selected_receipts:
        family_id = receipt["family_id"]
        visits[family_id] += 1
        savings[family_id] += float(receipt["savings_rub"])
        spend[family_id] += float(receipt["check_total_rub"])
    for item in items:
        family_id = receipt_family.get(item["receipt_id"])
        if family_id is None:
            continue
        item_counts[family_id] += 1
        category_counts[family_id][item["category"]] += 1
        promo_counts[family_id] += item["is_promo"] == "true"
        markdown_counts[family_id] += item["is_markdown"] == "true"

    public_rows: list[dict[str, object]] = []
    key_rows: list[dict[str, object]] = []
    for index, profile in enumerate(selected, start=1):
        family_id = profile["family_id"]
        total_items = item_counts[family_id]
        total_visits = visits[family_id]
        review_id = f"review_{index:03d}"
        public_rows.append({
            "review_id": review_id,
            "child_stage": profile["child_stage"],
            "network_home": profile["network_home"],
            "weeks_observed": len(recent_weeks),
            "visits": total_visits,
            "items": total_items,
            "observed_avg_check_rub": round(spend[family_id] / max(total_visits, 1), 2),
            "savings_rub": round(savings[family_id], 2),
            "avg_weekly_saving_rub": round(savings[family_id] / len(recent_weeks), 2),
            "promo_rate": round(promo_counts[family_id] / max(total_items, 1), 4),
            "markdown_rate": round(markdown_counts[family_id] / max(total_items, 1), 4),
            "top_categories": ";".join(
                category for category, _ in category_counts[family_id].most_common(5)
            ),
        })
        key_rows.append({
            "review_id": review_id,
            "family_id": family_id,
            "user_id": profile["user_id"],
            "behavior_type": profile["behavior_type"],
        })

    public_fields = list(public_rows[0]) if public_rows else []
    key_fields = list(key_rows[0]) if key_rows else []
    _write_csv(out_dir / "blind_review_profiles.csv", public_fields, public_rows)
    _write_csv(out_dir / "blind_review_key.csv", key_fields, key_rows)
    _write_csv(
        out_dir / "blind_review_ratings_template.csv",
        RATING_FIELDS,
        [{field: row["review_id"] if field == "review_id" else "" for field in RATING_FIELDS}
         for row in public_rows],
    )

    manifest = {
        "sample_size": len(selected),
        "requested_sample_size": sample_size,
        "seed": seed,
        "weeks_observed": len(recent_weeks),
        "child_stage_distribution": dict(
            sorted(Counter(row["child_stage"] for row in selected).items())
        ),
        "behavior_distribution_internal": dict(
            sorted(Counter(row["behavior_type"] for row in selected).items())
        ),
        "evaluator_files": [
            "blind_review_profiles.csv",
            "blind_review_ratings_template.csv",
        ],
        "internal_files": ["blind_review_key.csv"],
        "note": (
            "The evaluator must not receive the internal key or information "
            "about which system generated options A and B."
        ),
    }
    (out_dir / "blind_review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
