from __future__ import annotations

from typing import Iterable


def savings(receipt_items: Iterable[dict[str, object]]) -> float:
    from ai.policy import money, quantity
    return sum((money(item["price_shelf"]) - money(item["price_paid"])) * quantity(item.get("qty", 1))
               for item in receipt_items) / 100


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
