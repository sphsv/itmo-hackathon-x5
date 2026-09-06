"""One receipt reducer shared by replay, HTTP demo and evaluation.

SQLite stores immutable assignments and idempotent events, not derived balances.
Full returns have permanent tombstones, including return-before-sale delivery.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from ai.policy import RULE_VERSION, flag, money, quantity
from .exclusions import eligible_category, markdown_allowed


def normalize_receipt(payload):
    if not isinstance(payload, dict):
        raise ValueError("Receipt must be an object")
    for key in ("receipt_id", "family_id", "purchased_on"):
        if not isinstance(payload.get(key), str) or not payload[key] or len(payload[key]) > 160:
            raise ValueError(f"Invalid {key}")
    date.fromisoformat(payload["purchased_on"])
    if len(payload["purchased_on"]) != 10:
        raise ValueError("Date must use YYYY-MM-DD")
    items = payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 200:
        raise ValueError("Receipt must have 1..200 items")
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Item must be an object")
        category = item.get("category")
        if not isinstance(category, str) or not category or len(category) > 100:
            raise ValueError("Invalid category")
        shelf, paid = money(item.get("price_shelf")), money(item.get("price_paid"))
        if paid > shelf or shelf > 100_000_000:
            raise ValueError("Require paid <= shelf <= 1 million rubles")
        normalized.append({"category": category, "qty": quantity(item.get("qty", 1)),
                           "shelf_minor": shelf, "paid_minor": paid,
                           "is_markdown": flag(item.get("is_markdown", False))})
    return {k: payload[k] for k in ("receipt_id", "family_id", "purchased_on")} | {"items": normalized}


def receipt_amounts(receipt, goal):
    all_saving = eligible_saving = goal_saving = markdown_units = paid = 0
    eligible_items = 0
    for item in receipt["items"]:
        qty, cat = item["qty"], item["category"]
        saving = (item["shelf_minor"] - item["paid_minor"]) * qty
        paid += item["paid_minor"] * qty
        all_saving += saving
        if not eligible_category(cat):
            continue
        eligible_items += qty
        eligible_saving += saving
        is_markdown = item["is_markdown"] and markdown_allowed(cat)
        if is_markdown:
            markdown_units += qty
        if cat in goal["categories"] and (goal["mechanic"] != "markdown_saving" or is_markdown):
            goal_saving += saving
    return {"paid_minor": paid, "all_saving_minor": all_saving,
            "eligible_saving_minor": eligible_saving, "goal_saving_minor": goal_saving,
            "markdown_units": markdown_units, "eligible_items": eligible_items}


def reduce_receipts(goal, receipts, cancelled=()):
    cancelled = set(cancelled)
    totals = {key: 0 for key in ("paid_minor", "all_saving_minor", "eligible_saving_minor",
                                "goal_saving_minor", "markdown_units", "eligible_items")}
    active, days = [], set()
    seen = {}
    for receipt in sorted(receipts, key=lambda r: (r["purchased_on"], r["receipt_id"])):
        rid = receipt["receipt_id"]
        if rid in seen:
            if seen[rid] != receipt:
                raise ValueError("Conflicting receipt ID")
            continue
        seen[rid] = receipt
        if receipt["family_id"] != goal["family_id"]:
            raise ValueError("Receipt belongs to another family")
        if rid in cancelled or not goal["starts_on"] <= receipt["purchased_on"] < goal["ends_before"]:
            continue
        amounts = receipt_amounts(receipt, goal)
        active.append({"receipt_id": rid, "purchased_on": receipt["purchased_on"], **amounts})
        for key in totals:
            totals[key] += amounts[key]
        if amounts["eligible_items"]:
            days.add(receipt["purchased_on"])
    assigned = goal["status"] == "assigned"
    complete = assigned and totals["goal_saving_minor"] >= goal["target_saving_minor"]
    # No cash reward; configurable economic value must be validated in the pilot.
    raw_points = (totals["eligible_saving_minor"] // 500 + totals["markdown_units"] * 4
                  + (goal["reward_points"] if complete else 0)) if assigned else 0
    # Tenths of a centimeter eliminate floating-point drift.
    growth_tenths = min(50, len(days) * 8 + (20 if complete else 0)
                        + min(10, totals["markdown_units"] * 2)) if assigned else 0
    return {"assignment_id": goal["assignment_id"], "rule_version": goal.get("rule_version", RULE_VERSION),
            "variant_id": goal.get("variant_id"), "rollout_id": goal.get("rollout_id"),
            "status": "completed" if complete else goal["status"],
            "challenge_completed": complete, "totals": totals,
            "points": min(300, raw_points), "uncapped_points": raw_points,
            "weekly_points_cap": 300, "growth_cm": growth_tenths / 10,
            "weekly_growth_cap_cm": 5, "purchase_days": len(days),
            "remaining_saving_minor": max(0, goal["target_saving_minor"] - totals["goal_saving_minor"]),
            "receipts": active, "cancelled_receipt_ids": sorted(cancelled),
            "note": "Баллы демонстрационные, не рубли и не реальное начисление X5."}


class Ledger:
    def __init__(self, path: Path | str):
        self.db = sqlite3.connect(str(path), timeout=15)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS assignments(family TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, family TEXT NOT NULL,
              payload TEXT NOT NULL, FOREIGN KEY(family) REFERENCES assignments(family));
            CREATE TABLE IF NOT EXISTS cancellations(id TEXT PRIMARY KEY, family TEXT NOT NULL,
              FOREIGN KEY(family) REFERENCES assignments(family));
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,
              action TEXT NOT NULL, family TEXT NOT NULL, receipt_id TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    def assign(self, goal):
        encoded = json.dumps(goal, ensure_ascii=False, sort_keys=True)
        with self.db:
            row = self.db.execute("SELECT payload FROM assignments WHERE family=?", (goal["family_id"],)).fetchone()
            if row and row[0] != encoded:
                raise ValueError("Existing assignment is immutable: use a new demo database for another week/version")
            self.db.execute("INSERT OR IGNORE INTO assignments VALUES (?,?)", (goal["family_id"], encoded))

    def goal(self, family):
        if not isinstance(family, str) or not family or len(family) > 160:
            raise ValueError("Invalid family_id")
        row = self.db.execute("SELECT payload FROM assignments WHERE family=?", (family,)).fetchone()
        if not row:
            raise ValueError("Unknown family")
        return json.loads(row[0])

    def state(self, family):
        goal = self.goal(family)
        receipts = [json.loads(r[0]) for r in self.db.execute("SELECT payload FROM receipts WHERE family=?", (family,))]
        cancelled = [r[0] for r in self.db.execute("SELECT id FROM cancellations WHERE family=?", (family,))]
        result = reduce_receipts(goal, receipts, cancelled)
        result["audit"] = [{"action": r[0], "receipt_id": r[1],
                            "family_id": family, "assignment_id": goal["assignment_id"],
                            "variant_id": goal.get("variant_id"),
                            "rule_version": goal.get("rule_version", RULE_VERSION),
                            "rollout_id": goal.get("rollout_id")}
                           for r in self.db.execute(
            "SELECT action,receipt_id FROM audit WHERE family=? ORDER BY seq", (family,))]
        return result

    def submit(self, payload):
        receipt = normalize_receipt(payload)
        family, rid = receipt["family_id"], receipt["receipt_id"]
        goal = self.goal(family)
        if not goal["starts_on"] <= receipt["purchased_on"] < goal["ends_before"]:
            raise ValueError("Receipt outside the assigned week")
        encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT payload FROM receipts WHERE id=?", (rid,)).fetchone()
            tombstone = self.db.execute("SELECT family FROM cancellations WHERE id=?", (rid,)).fetchone()
            if tombstone and tombstone[0] != family:
                raise ValueError("Receipt ID belongs to another family")
            if row and row[0] != encoded:
                raise ValueError("Receipt ID reused with different content")
            action = "duplicate" if row else "receipt_accepted"
            self.db.execute("INSERT OR IGNORE INTO receipts VALUES (?,?,?)", (rid, family, encoded))
            self.db.execute("INSERT INTO audit(action,family,receipt_id) VALUES (?,?,?)", (action, family, rid))
        return {"action": action, "state": self.state(family)}

    def cancel(self, family, rid):
        self.goal(family)
        if not isinstance(rid, str) or not rid or len(rid) > 160:
            raise ValueError("Invalid receipt_id")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            for table in ("receipts", "cancellations"):
                owner = self.db.execute(f"SELECT family FROM {table} WHERE id=?", (rid,)).fetchone()
                if owner and owner[0] != family:
                    raise ValueError("Receipt ID belongs to another family")
            cursor = self.db.execute("INSERT OR IGNORE INTO cancellations VALUES (?,?)", (rid, family))
            action = "cancelled" if cursor.rowcount else "duplicate_cancellation"
            self.db.execute("INSERT INTO audit(action,family,receipt_id) VALUES (?,?,?)", (action, family, rid))
        return {"action": action, "state": self.state(family)}
