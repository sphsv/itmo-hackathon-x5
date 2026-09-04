from __future__ import annotations

from typing import Iterable


def savings(receipt_items: Iterable[dict[str, object]]) -> float:
    return round(sum(float(item["price_shelf"]) - float(item["price_paid"]) for item in receipt_items), 2)


def growth(visits: int, challenge_completed: bool, markdown_items: int) -> float:
    raw = visits * 0.8 + (2.0 if challenge_completed else 0.0) + min(markdown_items * 0.2, 1.0)
    return round(min(raw, 5.0), 2)


def points(saving_rub: float, markdown_items: int, challenge_completed: bool) -> int:
    raw = saving_rub * 0.20 + markdown_items * 4 + (25 if challenge_completed else 0)
    return min(300, round(raw))


def fraud_score(signals: dict[str, float | int | bool]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if int(signals.get("linked_families", 1)) >= 4:
        score += 30
        reasons.append("одна карта связана минимум с четырьмя семьями")
    if float(signals.get("refund_ratio", 0.0)) >= 0.50:
        score += 35
        reasons.append("доля возвратов не ниже 50%")
    if bool(signals.get("repetitive_markdown", False)):
        score += 25
        reasons.append("повторяющиеся уценённые SKU в коротком окне")
    if int(signals.get("referrals_24h", 0)) >= 5:
        score += 25
        reasons.append("не менее пяти рефералов за 24 часа")
    if bool(signals.get("employee_pattern", False)):
        score += 20
        reasons.append("паттерн покупок связан с одной кассой/сменой")
    return min(score, 100), reasons


def review_required(score: int, threshold: int = 70) -> bool:
    return score >= threshold


def referral_status(hours_since_purchase: float, cancelled: bool) -> str:
    if cancelled:
        return "cancelled"
    if hours_since_purchase < 72:
        return "pending"
    return "confirmed"
