from __future__ import annotations
import copy
import csv
import json
import tempfile
import threading
import unittest
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ai.policy import Dataset, POLICY_VERSION, RULE_VERSION, money, next_week, recommend_goal, variant
from ai.review import aggregate_ratings, prepare_review
from data import generate, prepare_target_dataset, prepare_blind_review_sample
from sim.exclusions import eligible_category
from sim.ledger import Ledger, normalize_receipt, reduce_receipts
from sim.rules import savings
from sim.simulate import league_table


def goal(fid="f"):
    return {"family_id": fid, "assignment_id": fid + ":2026-W37", "status": "assigned",
            "week": "2026-W37", "starts_on": "2026-09-07", "ends_before": "2026-09-14",
            "categories": ["молочка"], "mechanic": "habitual_saving",
            "target_saving_minor": 5000, "reward_points": 25,
            "policy_version": POLICY_VERSION, "rule_version": RULE_VERSION}


def receipt(rid="r1", fid="f", **item_changes):
    item = {"category": "молочка", "qty": 2, "price_shelf": "100.00", "price_paid": "75.00", "is_markdown": False}
    item.update(item_changes)
    return {"family_id": fid, "receipt_id": rid, "purchased_on": "2026-09-07", "items": [item]}


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "events.sqlite3"
        self.ledger = Ledger(self.path)
        self.ledger.assign(goal())

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_qty_exact_savings_completion(self):
        result = self.ledger.submit(receipt())["state"]
        self.assertEqual(result["totals"]["goal_saving_minor"], 5000)
        self.assertEqual(result["totals"]["paid_minor"], 15000)
        self.assertEqual(result["points"], 35)
        self.assertEqual(result["growth_cm"], 2.8)
        self.assertTrue(result["challenge_completed"])
        self.assertEqual(savings(receipt()["items"]), 50)
        self.assertEqual(money("0.29"), 29)

    def test_duplicate_and_payload_conflict(self):
        before = self.ledger.submit(receipt())["state"]
        duplicate = self.ledger.submit(receipt())
        self.assertEqual(duplicate["action"], "duplicate")
        self.assertEqual(before["points"], duplicate["state"]["points"])
        with self.assertRaises(ValueError):
            self.ledger.submit(receipt(qty=3))
        self.assertEqual(self.ledger.state("f")["points"], 35)

    def test_return_duplicate_return_persistence(self):
        self.ledger.submit(receipt())
        state = self.ledger.cancel("f", "r1")["state"]
        self.assertEqual(state["points"], 0)
        self.assertEqual(state["growth_cm"], 0)
        self.assertFalse(state["challenge_completed"])
        self.assertEqual(self.ledger.cancel("f", "r1")["action"], "duplicate_cancellation")
        second = Ledger(self.path)
        self.assertEqual(second.state("f")["points"], 0)
        self.assertEqual(second.state("f")["cancelled_receipt_ids"], ["r1"])
        second.close()

    def test_return_before_sale_and_cross_family(self):
        self.ledger.cancel("f", "r1")
        self.assertEqual(self.ledger.submit(receipt())["state"]["points"], 0)
        self.ledger.assign(goal("g"))
        with self.assertRaises(ValueError):
            self.ledger.submit(receipt(fid="g"))
        with self.assertRaises(ValueError):
            self.ledger.cancel("g", "r1")

    def test_excluded_and_unknown_never_earn(self):
        for cat in ["алкоголь", "табак", "детское пюре", "детские каши", "детские творожки", "заменители грудного молока", "unknown"]:
            with self.subTest(cat=cat):
                state = self.ledger.submit(receipt(rid=cat, category=cat, is_markdown=True))["state"]
                self.assertEqual(state["points"], 0)
                self.assertEqual(state["growth_cm"], 0)
                self.assertEqual(state["totals"]["eligible_saving_minor"], 0)

    def test_unqualified_receipt_does_not_complete(self):
        state = self.ledger.submit(receipt(category="хлеб"))["state"]
        self.assertFalse(state["challenge_completed"])
        self.assertEqual(state["totals"]["goal_saving_minor"], 0)

    def test_markdown_requires_actual_allowed_flag(self):
        g = goal()
        g["mechanic"] = "markdown_saving"
        self.assertFalse(reduce_receipts(g, [normalize_receipt(receipt())])["challenge_completed"])
        self.assertTrue(reduce_receipts(g, [normalize_receipt(receipt(is_markdown=True))])["challenge_completed"])

    def test_invalid_receipt_is_atomic(self):
        for changes in ({"qty": 0}, {"qty": -1}, {"qty": 1.5}, {"qty": True}, {"qty": "nan"},
                        {"price_paid": -1}, {"price_paid": "nan"}, {"price_paid": "inf"},
                        {"price_paid": "0.001"}, {"price_paid": 101}, {"is_markdown": "yes"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.ledger.submit(receipt(**changes))
        self.assertEqual(self.ledger.state("f")["receipts"], [])
        self.assertEqual(self.ledger.state("f")["audit"], [])

    def test_week_boundaries(self):
        for day in ("2026-09-06", "2026-09-14", "2026-02-30"):
            payload = receipt()
            payload["purchased_on"] = day
            with self.assertRaises(ValueError):
                self.ledger.submit(payload)
        payload = receipt()
        payload["purchased_on"] = "2026-09-13"
        self.assertTrue(self.ledger.submit(payload)["state"]["challenge_completed"])

    def test_cap_recomputed_after_return_and_order_independence(self):
        self.ledger.submit(receipt(rid="big", qty=1000, is_markdown=True))
        state = self.ledger.submit(receipt())["state"]
        self.assertEqual(state["points"], 300)
        self.assertLessEqual(state["growth_cm"], 5)
        state = self.ledger.cancel("f", "big")["state"]
        self.assertEqual(state["points"], 35)
        receipts = [normalize_receipt(receipt(rid="a")), normalize_receipt(receipt(rid="b"))]
        self.assertEqual(reduce_receipts(goal(), receipts), reduce_receipts(goal(), receipts[::-1]))
        self.assertEqual(reduce_receipts(goal(), receipts)["purchase_days"], 1)

    def test_assignment_immutable_and_pure_reducer_dedup(self):
        changed = goal()
        changed["target_saving_minor"] = 1000
        with self.assertRaises(ValueError):
            self.ledger.assign(changed)
        item = normalize_receipt(receipt())
        self.assertEqual(reduce_receipts(goal(), [item]), reduce_receipts(goal(), [item, item]))

    def test_deferred_goal_no_rewards(self):
        g = goal()
        g.update(status="deferred", categories=[], target_saving_minor=0)
        state = reduce_receipts(g, [normalize_receipt(receipt())])
        self.assertFalse(state["challenge_completed"])
        self.assertEqual(state["points"], 0)


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        generate(80, seed=17, history_weeks=12, root=cls.root)
        cls.data = Dataset(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_future_or_synthetic_label_leakage(self):
        data = self.data
        fid, week = "family_ivanovy", "2026-W33"
        before = data.features(fid, week)
        profile = copy.deepcopy(data.profiles[fid])
        first = recommend_goal(before, profile, week, consent=True)
        profile.update(behavior_type="охотник", top_categories="алкоголь", child_stage="2-3")
        self.assertEqual(first, recommend_goal(before, profile, week, consent=True))
        copied = copy.deepcopy(data)
        for r in copied.by_family[fid]:
            if r["week"] >= week:
                copied.items[r["receipt_id"]] = [receipt(category="алкоголь")["items"][0]]
        self.assertEqual(before, copied.features(fid, week))
        self.assertTrue(all(w < week for w in before["history_weeks"]))

    def test_consent_target_cold_start(self):
        fid, week = "family_ivanovy", "2026-W37"
        feature = self.data.features(fid, week)
        profile = self.data.profiles[fid]
        self.assertEqual(recommend_goal(feature, profile, week)["status"], "deferred")
        cold = self.data.features(fid, "2026-W25")
        self.assertEqual(recommend_goal(cold, profile, "2026-W25", consent=True)["status"], "deferred")
        changed = dict(profile, x5_segment="молодёжь")
        self.assertEqual(recommend_goal(feature, changed, week, consent=True)["status"], "deferred")

    def test_all_assigned_categories_grounded_and_safe(self):
        for fid, profile in self.data.profiles.items():
            feature = self.data.features(fid, "2026-W37")
            rec = recommend_goal(feature, profile, "2026-W37", consent=True)
            for category in rec["categories"]:
                self.assertTrue(eligible_category(category))
                self.assertGreaterEqual(feature["category_weeks"][category], 3)

    def test_week_rollover_and_stable_variants(self):
        self.assertEqual(next_week("2026-W53"), "2027-W01")
        self.assertEqual([variant(str(i)) for i in range(100)], [variant(str(i)) for i in range(100)])
        self.assertEqual(set(variant(str(i)) for i in range(100)), set("ABCD"))

    def test_sparse_markdown_falls_back_to_habitual_goal(self):
        feature = {"cutoff_exclusive": "2026-W37", "visits": 16,
                   "category_counts": {"молочка": 16}, "category_weeks": {"молочка": 8},
                   "weekly_saving_minor": {"молочка": {str(i): 5000 for i in range(8)}},
                   "markdown_weekly_minor": {"молочка": {str(i): 1000 for i in range(3)}}}
        profile = {"family_id": "f", "user_id": "u", "x5_segment": "дети до 3", "is_app_user": "true"}
        rec = recommend_goal(feature, profile, "2026-W37", consent=True)
        self.assertEqual(rec["status"], "assigned")
        self.assertEqual(rec["mechanic"], "habitual_saving")
        self.assertEqual(rec["target_saving_minor"], 2500)

    def test_review_packet_and_missing_ratings(self):
        prepare_target_dataset(self.root)
        prepare_blind_review_sample(10, root=self.root)
        prepare_review(self.root)
        template = self.root / "review/public/ratings_template.csv"
        report = aggregate_ratings(self.root, [template])
        self.assertEqual(report["status"], "not_measured")
        with template.open() as stream:
            rows = list(csv.DictReader(stream))
        row = rows[0]
        row["assessor_id"] = "test_only"
        for field in row:
            if field.endswith("1_5"):
                row[field] = "5"
        row["preferred_option"] = "A"
        path = self.root / "test_ratings.csv"
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        report = aggregate_ratings(self.root, [path])
        self.assertEqual(report["status"], "partial")
        with self.assertRaises(ValueError):
            aggregate_ratings(self.root, [path, path])

    def test_tied_league_has_no_purchase_estimate(self):
        profiles = [{"family_id": str(i), "network_home": "ТС5"} for i in range(5)]
        rows = league_table(profiles, {str(i): 25 for i in range(5)})
        self.assertTrue(all(row["rank"] == 1 and row["gap_to_top3_points"] == 0 for row in rows))
        self.assertTrue(all("estimated_purchase_rub" not in row for row in rows))


class ApiTests(unittest.TestCase):
    def test_fresh_process_import_order_and_cli(self):
        root = Path(__file__).resolve().parents[1]
        for command in ([sys.executable, "serve_demo.py", "--help"],
                        [sys.executable, "-c", "from sim.ledger import Ledger; from ai.policy import Dataset"],
                        [sys.executable, "-m", "ai.review", "--help"]):
            result = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_http_receipt_duplicate_pause_cancel_restart(self):
        from serve_demo import make_server
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proto").mkdir()
            bundle = {"families": {"f": {"goal": goal()}}}
            (root / "proto/demo.json").write_text(json.dumps(bundle))
            (root / "proto/index.html").write_text("demo")
            db = root / "test.sqlite3"
            server = make_server(root, db, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            def post(path, payload, origin=None):
                headers = {"Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = origin
                request = Request(url + path, data=json.dumps(payload).encode(), headers=headers)
                with urlopen(request, timeout=5) as response:
                    return json.load(response)
            try:
                self.assertEqual(post("/api/receipt", receipt())["state"]["points"], 35)
                self.assertEqual(post("/api/receipt", receipt())["action"], "duplicate")
                self.assertFalse(post("/api/rollout", {"enabled": False})["enabled"])
                with self.assertRaises(HTTPError) as cm:
                    post("/api/receipt", receipt(rid="new"))
                self.assertEqual(cm.exception.code, 409)
                cm.exception.close()
                self.assertEqual(post("/api/cancel", {"family_id": "f", "receipt_id": "r1"})["state"]["points"], 0)
                with self.assertRaises(HTTPError) as cm:
                    post("/api/rollout", {"enabled": True}, "https://evil.example")
                cm.exception.close()
                with self.assertRaises(HTTPError) as cm:
                    post("/api/cancel", {"family_id": {}, "receipt_id": "r1"})
                cm.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            ledger = Ledger(db)
            self.assertEqual(ledger.state("f")["points"], 0)
            ledger.close()


if __name__ == "__main__":
    unittest.main()
