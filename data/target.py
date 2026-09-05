from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from .generate import BABY_FOOD


TARGET_SEGMENT = "дети до 3"
TARGET_FILES = {
    "profiles": "target_profiles.csv",
    "receipts": "target_receipts.csv",
    "items": "target_receipt_items.csv",
}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def validate_target_rows(
    profiles: list[dict[str, str]],
    receipts: list[dict[str, str]],
    items: list[dict[str, str]],
) -> dict[str, object]:
    family_ids = [row["family_id"] for row in profiles]
    receipt_ids = [row["receipt_id"] for row in receipts]
    family_id_set = set(family_ids)
    receipt_id_set = set(receipt_ids)

    checks = {
        "dataset_is_not_empty": bool(profiles and receipts and items),
        "profiles_are_target_segment": all(
            row["x5_segment"] == TARGET_SEGMENT for row in profiles
        ),
        "child_stage_is_present": all(
            row["child_stage"] not in {"", "none"} for row in profiles
        ),
        "family_ids_are_unique": len(family_ids) == len(family_id_set),
        "receipt_ids_are_unique": len(receipt_ids) == len(receipt_id_set),
        "receipts_reference_profiles": all(
            row["family_id"] in family_id_set for row in receipts
        ),
        "items_reference_receipts": all(
            row["receipt_id"] in receipt_id_set for row in items
        ),
        "baby_food_is_not_marked_down": not any(
            row["category"] in BABY_FOOD and row["is_markdown"] == "true"
            for row in items
        ),
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "checks": checks,
        "failed_checks": failed_checks,
        "counts": {
            "profiles": len(profiles),
            "receipts": len(receipts),
            "items": len(items),
        },
        "child_stage_distribution": dict(
            sorted(Counter(row["child_stage"] for row in profiles).items())
        ),
        "behavior_distribution": dict(
            sorted(Counter(row["behavior_type"] for row in profiles).items())
        ),
    }


def prepare_target_dataset(root: Path | str = Path(".")) -> dict[str, object]:
    root = Path(root)
    out_dir = root / "data" / "out"
    profile_fields, all_profiles = _read_csv(out_dir / "profiles.csv")
    receipt_fields, all_receipts = _read_csv(out_dir / "receipts.csv")
    item_fields, all_items = _read_csv(out_dir / "receipt_items.csv")

    profiles = [
        row for row in all_profiles if row["x5_segment"] == TARGET_SEGMENT
    ]
    family_ids = {row["family_id"] for row in profiles}
    receipts = [
        row for row in all_receipts if row["family_id"] in family_ids
    ]
    receipt_ids = {row["receipt_id"] for row in receipts}
    items = [
        row for row in all_items if row["receipt_id"] in receipt_ids
    ]

    report = validate_target_rows(profiles, receipts, items)
    if report["status"] != "passed":
        failed = ", ".join(report["failed_checks"])
        raise ValueError(f"Target dataset validation failed: {failed}")

    _write_csv(out_dir / TARGET_FILES["profiles"], profile_fields, profiles)
    _write_csv(out_dir / TARGET_FILES["receipts"], receipt_fields, receipts)
    _write_csv(out_dir / TARGET_FILES["items"], item_fields, items)
    (out_dir / "target_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
