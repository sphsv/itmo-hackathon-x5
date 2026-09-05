from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ai import evaluate, run_agent
from data import generate, prepare_target_dataset, validate_target_rows
from proto import build
from sim import simulate
from sim.rules import fraud_score, referral_status, review_required


class PocTests(unittest.TestCase):
    def test_end_to_end_and_safety_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_result = generate(60, seed=42, history_weeks=12, root=root)
            self.assertEqual(data_result["families"], 60)
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


if __name__ == "__main__":
    unittest.main()
