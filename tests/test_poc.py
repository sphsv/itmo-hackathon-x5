from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from ai import evaluate, run_agent
from data import generate
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


if __name__ == "__main__":
    unittest.main()
