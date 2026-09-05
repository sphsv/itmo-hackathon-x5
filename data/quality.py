from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from .generate import (
    BABY_FOOD,
    EXCLUDED,
    NETWORK_WEIGHTS,
    SEGMENTS,
    SEGMENT_WEIGHTS,
)


EXPECTED_SCHEMAS = {
    "profiles.csv": [
        "user_id", "family_id", "network_home", "x5_segment", "is_app_user",
        "behavior_type", "child_stage", "city_bucket", "base_freq_per_week",
        "avg_check_rub", "promo_share", "markdown_share", "top_categories",
    ],
    "receipts.csv": [
        "receipt_id", "family_id", "user_id", "week", "network_home",
        "check_total_rub", "savings_rub", "items_count",
    ],
    "receipt_items.csv": [
        "receipt_id", "sku", "category", "qty", "price_shelf", "price_paid",
        "is_promo", "is_markdown", "is_excluded",
    ],
}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source_dataset(root: Path | str = Path(".")) -> dict[str, object]:
    root = Path(root)
    out_dir = root / "data" / "out"
    loaded = {
        filename: _read_csv(out_dir / filename)
        for filename in EXPECTED_SCHEMAS
    }
    profile_fields, profiles = loaded["profiles.csv"]
    receipt_fields, receipts = loaded["receipts.csv"]
    item_fields, items = loaded["receipt_items.csv"]

    profile_ids = [row["family_id"] for row in profiles]
    receipt_ids = [row["receipt_id"] for row in receipts]
    profile_id_set = set(profile_ids)
    receipt_id_set = set(receipt_ids)
    profile_by_family = {row["family_id"]: row for row in profiles}
    receipt_by_id = {row["receipt_id"]: row for row in receipts}

    item_counts: Counter[str] = Counter()
    paid_by_receipt: defaultdict[str, float] = defaultdict(float)
    savings_by_receipt: defaultdict[str, float] = defaultdict(float)
    markdown_by_behavior: Counter[str] = Counter()
    items_by_behavior: Counter[str] = Counter()
    for item in items:
        receipt_id = item["receipt_id"]
        item_counts[receipt_id] += 1
        shelf = float(item["price_shelf"])
        paid = float(item["price_paid"])
        paid_by_receipt[receipt_id] += paid
        savings_by_receipt[receipt_id] += shelf - paid
        receipt = receipt_by_id.get(receipt_id)
        if receipt is not None:
            profile = profile_by_family.get(receipt["family_id"])
            if profile is not None:
                behavior = profile["behavior_type"]
                items_by_behavior[behavior] += 1
                markdown_by_behavior[behavior] += item["is_markdown"] == "true"

    segment_counts = Counter(row["x5_segment"] for row in profiles)
    network_counts = Counter(row["network_home"] for row in profiles)
    actual_segment_share = {
        segment: segment_counts[segment] / max(len(profiles), 1)
        for segment in SEGMENTS
    }
    expected_segment_share = {
        segment: sum(
            network_counts[network] / max(len(profiles), 1)
            * SEGMENT_WEIGHTS[network][index]
            for network in NETWORK_WEIGHTS
        )
        for index, segment in enumerate(SEGMENTS)
    }
    segment_deviation_pp = {
        segment: round(
            abs(actual_segment_share[segment] - expected_segment_share[segment]) * 100,
            2,
        )
        for segment in SEGMENTS
    }

    target_profiles = [row for row in profiles if row["x5_segment"] == "дети до 3"]
    other_profiles = [row for row in profiles if row["x5_segment"] != "дети до 3"]
    avg_check_target = _mean([float(row["avg_check_rub"]) for row in target_profiles])
    avg_check_other = _mean([float(row["avg_check_rub"]) for row in other_profiles])
    frequency_target = _mean([float(row["base_freq_per_week"]) for row in target_profiles])
    frequency_other = _mean([float(row["base_freq_per_week"]) for row in other_profiles])
    markdown_rates = {
        behavior: markdown_by_behavior[behavior] / max(items_by_behavior[behavior], 1)
        for behavior in ["хозяин", "охотник", "категорийный"]
    }

    schemas_match = (
        profile_fields == EXPECTED_SCHEMAS["profiles.csv"]
        and receipt_fields == EXPECTED_SCHEMAS["receipts.csv"]
        and item_fields == EXPECTED_SCHEMAS["receipt_items.csv"]
    )
    receipt_totals_match = all(
        abs(float(row["check_total_rub"]) - paid_by_receipt[row["receipt_id"]]) <= 0.10
        and abs(float(row["savings_rub"]) - savings_by_receipt[row["receipt_id"]]) <= 0.10
        for row in receipts
    )
    checks = {
        "expected_schemas": schemas_match,
        "tables_are_not_empty": bool(profiles and receipts and items),
        "family_ids_are_unique": len(profile_ids) == len(profile_id_set),
        "receipt_ids_are_unique": len(receipt_ids) == len(receipt_id_set),
        "receipts_reference_profiles": all(
            row["family_id"] in profile_id_set for row in receipts
        ),
        "items_reference_receipts": all(
            row["receipt_id"] in receipt_id_set for row in items
        ),
        "receipt_item_counts_match": all(
            item_counts[row["receipt_id"]] == int(row["items_count"])
            for row in receipts
        ),
        "receipt_amounts_reconcile": receipt_totals_match,
        "item_prices_are_valid": all(
            0 <= float(row["price_paid"]) <= float(row["price_shelf"])
            for row in items
        ),
        "excluded_flags_match_categories": all(
            (row["is_excluded"] == "true") == (row["category"] in EXCLUDED)
            for row in items
        ),
        "baby_food_is_not_marked_down": not any(
            row["category"] in BABY_FOOD and row["is_markdown"] == "true"
            for row in items
        ),
        "child_stage_matches_segment": all(
            (row["child_stage"] != "none") == (row["x5_segment"] == "дети до 3")
            for row in profiles
        ),
        "all_profiles_are_app_users": all(
            row["is_app_user"] == "true" for row in profiles
        ),
        "at_least_eight_weeks": len({row["week"] for row in receipts}) >= 8,
        "segment_share_within_1pp": all(
            deviation <= 1.0 for deviation in segment_deviation_pp.values()
        ),
        "target_avg_check_is_higher": avg_check_target > avg_check_other,
        "target_frequency_is_higher": frequency_target > frequency_other,
        "hunter_markdown_rate_is_higher": (
            markdown_rates["охотник"] > markdown_rates["хозяин"]
            and markdown_rates["охотник"] > markdown_rates["категорийный"]
        ),
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    report = {
        "status": "passed" if not failed_checks else "failed",
        "checks": checks,
        "failed_checks": failed_checks,
        "counts": {
            "profiles": len(profiles),
            "receipts": len(receipts),
            "items": len(items),
            "weeks": len({row["week"] for row in receipts}),
        },
        "metrics": {
            "actual_segment_share": {
                key: round(value, 4) for key, value in actual_segment_share.items()
            },
            "expected_segment_share": {
                key: round(value, 4) for key, value in expected_segment_share.items()
            },
            "segment_deviation_pp": segment_deviation_pp,
            "avg_check_rub": {
                "target": round(avg_check_target, 2),
                "other": round(avg_check_other, 2),
            },
            "base_frequency_per_week": {
                "target": round(frequency_target, 3),
                "other": round(frequency_other, 3),
            },
            "markdown_rate_by_behavior": {
                key: round(value, 4) for key, value in markdown_rates.items()
            },
        },
        "sha256": {
            filename: _fingerprint(out_dir / filename)
            for filename in EXPECTED_SCHEMAS
        },
        "note": (
            "Synthetic data quality report. Distribution and behavior checks "
            "validate generator assumptions, not real customer behavior."
        ),
    }
    (out_dir / "data_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
