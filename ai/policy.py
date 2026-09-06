"""Versioned, history-only weekly policy. No synthetic labels or LLM required."""
from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median

from sim.exclusions import eligible_category, markdown_allowed

POLICY_VERSION = "family-goal-v2.0"
RULE_VERSION = "receipt-ledger-v2.0"


def money(value) -> int:
    """Input rubles, exact integer kopecks. Reject nonfinite/negative/subkopeck."""
    try:
        number = Decimal(str(value)) * 100
        if not number.is_finite() or number < 0 or number != number.to_integral_value():
            raise ValueError("Price must be nonnegative rubles with at most two decimals")
        return int(number)
    except InvalidOperation as exc:
        raise ValueError("Invalid price") from exc


def quantity(value) -> int:
    if isinstance(value, bool):
        raise ValueError("Quantity must be a positive integer")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 1 or number > 10000 or number != number.to_integral_value():
            raise ValueError("Quantity must be an integer in 1..10000")
        return int(number)
    except InvalidOperation as exc:
        raise ValueError("Invalid quantity") from exc


def flag(value) -> bool:
    if value is True or value == "true":
        return True
    if value is False or value == "false":
        return False
    raise ValueError("Boolean flag must be true or false")


def week_start(week: str) -> date:
    year, number = week.split("-W")
    return date.fromisocalendar(int(year), int(number), 1)


def next_week(week: str) -> str:
    day = week_start(week) + timedelta(days=7)
    year, number, _ = day.isocalendar()
    return f"{year}-W{number:02}"


def read_csv(path: Path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class Dataset:
    def __init__(self, root: Path):
        base = Path(root) / "data" / "out"
        self.profiles = {p["family_id"]: p for p in read_csv(base / "profiles.csv")}
        self.receipts = read_csv(base / "receipts.csv")
        self.weeks = sorted({r["week"] for r in self.receipts})
        self.items = defaultdict(list)
        for row in read_csv(base / "receipt_items.csv"):
            self.items[row["receipt_id"]].append(row)
        self.by_family = defaultdict(list)
        for row in self.receipts:
            self.by_family[row["family_id"]].append(row)

    def features(self, family_id: str, cutoff: str):
        # Calendar window, not last eight observed weeks (zero weeks matter).
        start = week_start(cutoff) - timedelta(weeks=8)
        history = [r for r in self.by_family[family_id]
                   if start <= week_start(r["week"]) < week_start(cutoff)]
        counts, category_weeks = Counter(), defaultdict(set)
        weekly = defaultdict(lambda: defaultdict(int))
        markdown_weekly = defaultdict(lambda: defaultdict(int))
        for receipt in history:
            week = receipt["week"]
            for item in self.items[receipt["receipt_id"]]:
                cat, qty = item["category"], quantity(item["qty"])
                if not eligible_category(cat):
                    continue
                saving = max(0, money(item["price_shelf"]) - money(item["price_paid"])) * qty
                counts[cat] += qty
                category_weeks[cat].add(week)
                weekly[cat][week] += saving
                if flag(item["is_markdown"]) and markdown_allowed(cat):
                    markdown_weekly[cat][week] += saving
        return {
            "family_id": family_id, "cutoff_exclusive": cutoff,
            "history_start": start.isoformat(), "visits": len(history),
            "category_counts": dict(counts),
            "category_weeks": {k: len(v) for k, v in category_weeks.items()},
            "weekly_saving_minor": {k: dict(v) for k, v in weekly.items()},
            "markdown_weekly_minor": {k: dict(v) for k, v in markdown_weekly.items()},
            "history_weeks": sorted({r["week"] for r in history}),
        }


def recommend_goal(feature, profile, week: str, *, consent: bool = False, baseline=False):
    if feature["cutoff_exclusive"] != week:
        raise ValueError("Feature cutoff must equal assignment week")
    start = week_start(week)
    result = {
        "family_id": profile["family_id"], "user_id": profile["user_id"],
        # Profile and shopping situation are separate axes.  The context is an
        # assignment-week assumption for this PoC, not a discovered AJTBD label.
        "x5_segment": profile.get("x5_segment"),
        "job_context": {
            "level": "family_week",
            "code": "planned_family_shop_budget_control",
            "status": "synthetic_scenario_not_observed",
        },
        "assignment_id": f"{profile['family_id']}:{week}:{'static' if baseline else POLICY_VERSION}",
        "policy_version": "static-v1" if baseline else POLICY_VERSION,
        "rule_version": RULE_VERSION, "variant_id": variant(profile["family_id"]),
        "rollout_id": "pilot-v1-fixed-cohort", "rollout_percent": 100,
        "week": week,
        "starts_on": start.isoformat(), "ends_before": (start + timedelta(days=7)).isoformat(),
        "status": "deferred", "categories": [], "target_saving_minor": 0,
        "mechanic": "habitual_saving", "reward_points": 25,
        "history": feature,
        "disclaimer": "Суммируется экономия в любой из указанных категорий за неделю. Только если продукты уже в вашем плане: дополнительные покупки не нужны, цель можно пропустить.",
    }
    if not consent or profile.get("x5_segment") != "дети до 3" or profile.get("is_app_user") != "true":
        result["reason"] = "Нужны взрослый участник целевого сегмента, приложение и явное согласие."
        return result
    counts = feature["category_counts"]
    candidates = sorted((c for c in counts if eligible_category(c)
                         and feature["category_weeks"].get(c, 0) >= 3),
                        key=lambda c: (-counts[c], c))
    if feature["visits"] < 3 or not candidates:
        result["reason"] = "Недостаточно истории привычных безопасных категорий; показываем обычную лояльность."
        return result
    categories = candidates[:2]
    markdown_candidates = [c for c in candidates if markdown_allowed(c)
                           and sum(v > 0 for v in feature["markdown_weekly_minor"].get(c, {}).values()) >= 3]
    source = feature["weekly_saving_minor"]
    if markdown_candidates and not baseline:
        categories = markdown_candidates[:2]
        source = feature["markdown_weekly_minor"]
        result["mechanic"] = "markdown_saving"
    if baseline:
        categories = ["молочка", "хлеб"]
    totals = Counter()
    for cat in categories:
        totals.update(source.get(cat, {}))
    values = sorted(list(totals.values()) + [0] * max(0, 8 - len(totals)))
    # A modest, achievable threshold. Never recommend an increased basket size.
    typical = int(median(values))
    if typical < 100 and result["mechanic"] == "markdown_saving" and not baseline:
        # Sparse markdown must not hide a feasible habitual-basket goal.
        result["mechanic"] = "habitual_saving"
        categories = candidates[:2]
        totals = Counter()
        for cat in categories:
            totals.update(feature["weekly_saving_minor"].get(cat, {}))
        values = sorted(list(totals.values()) + [0] * max(0, 8 - len(totals)))
        typical = int(median(values))
    if typical < 100 and not baseline:
        result["reason"] = "Недостаточно повторяющейся экономии; не обещаем доступную скидку."
        return result
    target = 5000 if baseline else max(100, min(15000, (typical // 200) * 100))
    result.update(status="assigned", categories=categories, target_saving_minor=target)
    qualifier = "на уценённых продуктах" if result["mechanic"] == "markdown_saving" else "по скидкам"
    result["title"] = f"Сэкономьте {target / 100:g} ₽ {qualifier}: {', '.join(categories)}"
    result["reason"] = (
        f"За предыдущие 8 недель: {feature['visits']} чеков. "
        f"Категории встречались минимум в 3 неделях. Медиана недельной экономии в них: {typical / 100:g} ₽. "
        "Порог — половина этой медианы, до 150 ₽. Это ориентир истории, не прогноз наличия скидок."
        if not baseline else "Одинаковая цель для всех: 50 ₽ в категориях молочка и хлеб; та же награда и правила."
    )
    return result


def variant(family_id: str, salt="pilot-v1") -> str:
    return "ABCD"[int(hashlib.sha256(f"{salt}:{family_id}".encode()).hexdigest()[:8], 16) % 4]
