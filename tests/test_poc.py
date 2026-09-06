from __future__ import annotations

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from ai import evaluate, run_agent
from data import (
    generate,
    prepare_blind_review_sample,
    prepare_fraud_benchmark,
    prepare_target_dataset,
    validate_target_rows,
    validate_source_dataset,
)
from proto import build
from sim import simulate
from sim.rules import fraud_score, referral_status, review_required


class PocTests(unittest.TestCase):
    def test_end_to_end_and_safety_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_result = generate(60, seed=42, history_weeks=12, root=root)
            self.assertEqual(data_result["families"], 60)
            quality_result = validate_source_dataset(root)
            structural_checks = [
                "expected_schemas",
                "tables_are_not_empty",
                "family_ids_are_unique",
                "receipt_ids_are_unique",
                "receipts_reference_profiles",
                "items_reference_receipts",
                "receipt_item_counts_match",
                "receipt_amounts_reconcile",
                "item_prices_are_valid",
                "excluded_flags_match_categories",
                "baby_food_is_not_marked_down",
                "child_stage_matches_segment",
            ]
            self.assertTrue(all(quality_result["checks"][name] for name in structural_checks))
            with (root / "data" / "out" / "receipt_items.csv").open(encoding="utf-8") as fh:
                items = list(csv.DictReader(fh))
            forbidden_markdown = {
                "детское пюре", "детские каши", "детские творожки", "заменители грудного молока"
            }
            self.assertFalse(any(row["category"] in forbidden_markdown and row["is_markdown"] == "true" for row in items))

            target_result = prepare_target_dataset(root)
            self.assertEqual(target_result["status"], "passed")
            self.assertGreater(target_result["counts"]["profiles"], 0)
            with (root / "data" / "out" / "target_profiles.csv").open(encoding="utf-8") as fh:
                target_profiles = list(csv.DictReader(fh))
            self.assertTrue(all(row["x5_segment"] == "дети до 3" for row in target_profiles))

            review_result = prepare_blind_review_sample(10, seed=42, root=root)
            self.assertEqual(review_result["sample_size"], 10)
            with (root / "data" / "out" / "blind_review_profiles.csv").open(encoding="utf-8") as fh:
                review_profiles = list(csv.DictReader(fh))
            with (root / "data" / "out" / "blind_review_key.csv").open(encoding="utf-8") as fh:
                review_key = list(csv.DictReader(fh))
            self.assertEqual(len(review_profiles), 10)
            self.assertEqual(len(review_key), 10)
            self.assertNotIn("family_id", review_profiles[0])
            self.assertNotIn("behavior_type", review_profiles[0])
            self.assertEqual(
                {row["review_id"] for row in review_profiles},
                {row["review_id"] for row in review_key},
            )

            fraud_result = prepare_fraud_benchmark(root)
            self.assertEqual(fraud_result["cases"], 40)
            self.assertEqual(
                fraud_result["cohorts"],
                {"normal": 20, "borderline": 10, "fraud": 10},
            )
            threshold_70 = next(
                row for row in fraud_result["threshold_metrics"]
                if row["threshold"] == 70
            )
            self.assertGreater(threshold_70["precision"], 0)
            self.assertGreater(threshold_70["recall"], 0)
            self.assertLess(threshold_70["recall"], 1)

            agent_result = run_agent(30, seed=42, root=root)
            self.assertEqual(agent_result["sample"], 30)
            eval_result = evaluate(root)
            self.assertGreaterEqual(eval_result["constraints_pass_rate"], 1.0)
            self.assertGreaterEqual(eval_result["personalized_behavior_accuracy"], 0.70)
            self.assertGreater(eval_result["personalized_behavior_accuracy"], eval_result["static_one_size_fits_all_accuracy"])
            sim_result = simulate(8, seed=42, root=root)
            self.assertEqual(sim_result["families"], 60)
            proto_result = build(root)
            self.assertTrue(Path(proto_result["prototype"]).exists())

    def test_explainable_fraud_threshold(self) -> None:
        score, reasons = fraud_score({
            "linked_families": 5,
            "refund_ratio": 0.65,
            "repetitive_markdown": True,
        })
        self.assertEqual(score, 90)
        self.assertTrue(review_required(score))
        self.assertEqual(len(reasons), 3)
        self.assertEqual(referral_status(48, False), "pending")
        self.assertEqual(referral_status(80, False), "confirmed")
        self.assertEqual(referral_status(80, True), "cancelled")

    def test_target_validation_detects_broken_references(self) -> None:
        report = validate_target_rows(
            profiles=[{
                "family_id": "family_1", "x5_segment": "дети до 3",
                "child_stage": "1-2", "behavior_type": "хозяин",
            }],
            receipts=[{"receipt_id": "receipt_1", "family_id": "family_missing"}],
            items=[{
                "receipt_id": "receipt_missing", "category": "молочка",
                "is_markdown": "false",
            }],
        )
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["checks"]["receipts_reference_profiles"])
        self.assertFalse(report["checks"]["items_reference_receipts"])

    def test_generation_is_reproducible_for_same_seed(self) -> None:
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first_root = Path(first_tmp)
            second_root = Path(second_tmp)
            generate(80, seed=17, history_weeks=12, root=first_root)
            generate(80, seed=17, history_weeks=12, root=second_root)
            for filename in ["profiles.csv", "receipts.csv", "receipt_items.csv"]:
                first = hashlib.sha256(
                    (first_root / "data" / "out" / filename).read_bytes()
                ).digest()
                second = hashlib.sha256(
                    (second_root / "data" / "out" / filename).read_bytes()
                ).digest()
                self.assertEqual(first, second, filename)


if __name__ == "__main__":
    unittest.main()
