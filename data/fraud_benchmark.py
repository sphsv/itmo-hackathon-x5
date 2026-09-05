from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from sim.rules import fraud_score


SIGNAL_FIELDS = [
    "linked_families",
    "refund_ratio",
    "repetitive_markdown",
    "referrals_24h",
    "employee_pattern",
]


def _case(
    cohort: str,
    rationale: str,
    linked_families: int = 1,
    refund_ratio: float = 0.0,
    repetitive_markdown: bool = False,
    referrals_24h: int = 0,
    employee_pattern: bool = False,
) -> dict[str, object]:
    return {
        "cohort": cohort,
        "linked_families": linked_families,
        "refund_ratio": refund_ratio,
        "repetitive_markdown": repetitive_markdown,
        "referrals_24h": referrals_24h,
        "employee_pattern": employee_pattern,
        "label_rationale": rationale,
    }


def _scenario_specs() -> list[dict[str, object]]:
    normal = [
        _case("normal", "Обычная семейная карта без риск-сигналов", refund_ratio=0.02),
        _case("normal", "Два взрослых используют одну семейную карту", linked_families=2, refund_ratio=0.04),
        _case("normal", "Три подтверждённых участника одной семьи", linked_families=3, refund_ratio=0.03),
        _case("normal", "Единичные возвраты обычных товаров", refund_ratio=0.18),
        _case("normal", "Сезонный рост возвратов ниже порога", refund_ratio=0.42),
        _case("normal", "Регулярная покупка уценённого хлеба без других сигналов", repetitive_markdown=True),
        _case("normal", "Органический реферальный отклик ниже порога", referrals_24h=4),
        _case("normal", "Покупки сотрудника без аномалий", employee_pattern=True),
        _case("normal", "Большая подтверждённая семья без иных сигналов", linked_families=4),
        _case("normal", "Возврат брака без иных сигналов", refund_ratio=0.53),
        _case("normal", "Пять приглашений после семейного мероприятия", referrals_24h=5),
        _case("normal", "Уценка одного SKU и редкие возвраты", refund_ratio=0.12, repetitive_markdown=True),
        _case("normal", "Сотрудник участвует в обычной реферальной кампании", referrals_24h=2, employee_pattern=True),
        _case("normal", "Подтверждённая большая семья и низкие возвраты", linked_families=4, refund_ratio=0.08),
        _case("normal", "Продуктовый отзыв вызвал возвраты у постоянного покупателя", refund_ratio=0.58, linked_families=2),
        _case("normal", "Постоянная уценка и участие сотрудника проверены вручную", repetitive_markdown=True, employee_pattern=True),
        _case("normal", "Большая семья покупает один и тот же уценённый хлеб", linked_families=4, repetitive_markdown=True),
        _case("normal", "Возврат отозванного товара совпал с реферальной кампанией", refund_ratio=0.57, referrals_24h=5),
        _case("normal", "Подтверждённый сотрудник использует общую карту семьи", linked_families=4, employee_pattern=True),
        _case("normal", "Внутренний тестовый профиль должен исключаться до скоринга", refund_ratio=0.61, referrals_24h=6, employee_pattern=True),
    ]
    borderline = [
        _case("borderline", "Нужно подтвердить состав большой семьи и повтор SKU", linked_families=4, repetitive_markdown=True),
        _case("borderline", "Высокие возвраты совпали с повторной уценкой", refund_ratio=0.52, repetitive_markdown=True),
        _case("borderline", "Реферальный всплеск связан с одной кассой", referrals_24h=5, employee_pattern=True),
        _case("borderline", "Большая семья и высокий возврат требуют документов", linked_families=4, refund_ratio=0.56),
        _case("borderline", "Повтор SKU и рефералы могут быть кампанией или злоупотреблением", repetitive_markdown=True, referrals_24h=5),
        _case("borderline", "Паттерн сотрудника и возвраты требуют проверки смены", refund_ratio=0.51, employee_pattern=True),
        _case("borderline", "Три умеренных сигнала без подтверждённого ущерба", linked_families=4, repetitive_markdown=True, employee_pattern=True),
        _case("borderline", "Возвраты и рефералы находятся ровно на порогах", refund_ratio=0.50, referrals_24h=5),
        _case("borderline", "Много связей и рефералов могут относиться к одному домохозяйству", linked_families=5, referrals_24h=6),
        _case("borderline", "Уценка, рефералы и сотрудник требуют ручной проверки", repetitive_markdown=True, referrals_24h=5, employee_pattern=True),
    ]
    fraud = [
        _case("fraud", "Одна карта массово привязана к семьям, возвраты и SKU повторяются", linked_families=5, refund_ratio=0.68, repetitive_markdown=True),
        _case("fraud", "Сотрудник проводит повторную уценку с последующими возвратами", refund_ratio=0.72, repetitive_markdown=True, employee_pattern=True),
        _case("fraud", "Реферальная ферма использует массовые связи и быстрые приглашения", linked_families=7, referrals_24h=11),
        _case("fraud", "Возвратная схема объединяет семьи, рефералы и высокий refund ratio", linked_families=6, refund_ratio=0.81, referrals_24h=8),
        _case("fraud", "Все доступные сигналы подтверждены расследованием", linked_families=8, refund_ratio=0.76, repetitive_markdown=True, referrals_24h=12, employee_pattern=True),
        _case("fraud", "Повторная уценка и реферальные аккаунты созданы одним оператором", repetitive_markdown=True, referrals_24h=9, employee_pattern=True),
        _case("fraud", "Сеть связанных семей использует одну кассу", linked_families=6, employee_pattern=True),
        _case("fraud", "Подтверждённая возвратная схема пока видна только по возвратам и кассе", refund_ratio=0.84, employee_pattern=True),
        _case("fraud", "Подтверждённая реферальная ферма пока даёт два слабых сигнала", referrals_24h=14, employee_pattern=True),
        _case("fraud", "Сговор по уценке подтверждён, но дополнительные признаки ещё не поступили", repetitive_markdown=True, employee_pattern=True),
    ]
    return normal + borderline + fraud


def _threshold_metrics(rows: list[dict[str, object]], threshold: int) -> dict[str, object]:
    certain = [row for row in rows if row["cohort"] != "borderline"]
    tp = sum(row["cohort"] == "fraud" and int(row["score_v0"]) >= threshold for row in certain)
    fp = sum(row["cohort"] == "normal" and int(row["score_v0"]) >= threshold for row in certain)
    tn = sum(row["cohort"] == "normal" and int(row["score_v0"]) < threshold for row in certain)
    fn = sum(row["cohort"] == "fraud" and int(row["score_v0"]) < threshold for row in certain)
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "borderline_sent_to_review": sum(
            row["cohort"] == "borderline" and int(row["score_v0"]) >= threshold
            for row in rows
        ),
    }


def prepare_fraud_benchmark(root: Path | str = Path(".")) -> dict[str, object]:
    root = Path(root)
    out_dir = root / "data" / "out"
    specs = _scenario_specs()
    rows: list[dict[str, object]] = []
    for index, spec in enumerate(specs, start=1):
        signals = {field: spec[field] for field in SIGNAL_FIELDS}
        score, reasons = fraud_score(signals)
        cohort = str(spec["cohort"])
        rows.append({
            "case_id": f"fraud_case_{index:03d}",
            "cohort": cohort,
            "is_fraud": {"normal": "false", "borderline": "unknown", "fraud": "true"}[cohort],
            **signals,
            "score_v0": score,
            "review_at_70": str(score >= 70).lower(),
            "score_reasons": "; ".join(reasons),
            "label_rationale": spec["label_rationale"],
        })

    cohort_counts = Counter(str(row["cohort"]) for row in rows)
    expected_counts = {"normal": 20, "borderline": 10, "fraud": 10}
    if dict(cohort_counts) != expected_counts:
        raise ValueError(f"Unexpected cohort counts: {dict(cohort_counts)}")

    fields = list(rows[0])
    with (out_dir / "fraud_benchmark.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "cases": len(rows),
        "cohorts": expected_counts,
        "threshold_metrics": [
            _threshold_metrics(rows, threshold) for threshold in [40, 50, 60, 70, 80, 90]
        ],
        "limitations": [
            "Сценарии экспертно заданы и не являются реальными antifraud-данными X5.",
            "Пограничные случаи исключены из precision и recall до ручной разметки.",
            "Метрики показывают поведение ruleset v0, а не production-качество.",
        ],
    }
    (out_dir / "fraud_benchmark_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
