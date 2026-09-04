from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

from .rules import fraud_score, growth, points, review_required


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_svg(path: Path, title: str, values: dict[str, float], suffix: str = "") -> None:
    width, height = 760, 420
    max_value = max(values.values(), default=1) or 1
    rows = []
    for i, (label, value) in enumerate(values.items()):
        y = 95 + i * 62
        bar = 460 * value / max_value
        rows.append(
            f'<text x="32" y="{y + 22}" font-size="16" fill="#333">{label}</text>'
            f'<rect x="210" y="{y}" width="{bar:.1f}" height="30" rx="5" fill="#00a34f"/>'
            f'<text x="{220 + bar:.1f}" y="{y + 21}" font-size="15" fill="#333">{value:.1f}{suffix}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="32" y="48" font-family="Arial" font-size="25" font-weight="700" fill="#222">{title}</text>'
        + "".join(rows)
        + '<text x="32" y="395" font-family="Arial" font-size="12" fill="#777">Синтетика: иллюстрация механики, не доказательство uplift</text>'
        + '</svg>'
    )
    path.write_text(svg, encoding="utf-8")


def _league_chunks(profiles: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    groups: defaultdict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for profile in profiles:
        groups[(profile["network_home"], profile["x5_segment"])].append(profile)
    chunks: list[list[dict[str, str]]] = []
    small_by_network: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    ready_groups = []
    for (network, _), group in groups.items():
        if len(group) < 20:
            small_by_network[network].extend(group)
        else:
            ready_groups.append(group)
    fallback: list[dict[str, str]] = []
    for group in small_by_network.values():
        if len(group) < 20:
            fallback.extend(group)
        else:
            ready_groups.append(group)
    if fallback:
        ready_groups.append(fallback)
    for group in ready_groups:
        group.sort(key=lambda row: row["family_id"])
        if len(group) <= 50 or len(group) < 40:
            chunks.append(group)
            continue
        n_chunks = math.ceil(len(group) / 50)
        chunk_size = math.ceil(len(group) / n_chunks)
        chunks.extend(group[start : start + chunk_size] for start in range(0, len(group), chunk_size))
    return chunks


def simulate(weeks: int = 8, seed: int = 42, root: Path | str = Path(".")) -> dict[str, object]:
    root = Path(root)
    out_dir = root / "sim" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    profiles = _read(root / "data" / "out" / "profiles.csv")
    receipts = _read(root / "data" / "out" / "receipts.csv")
    items = _read(root / "data" / "out" / "receipt_items.csv")
    features = _read(root / "ai" / "out" / "features.csv")
    inferred = {row["family_id"]: row["inferred_behavior"] for row in features}
    receipt_family = {r["receipt_id"]: r["family_id"] for r in receipts}
    receipt_week = {r["receipt_id"]: r["week"] for r in receipts}
    selected_weeks = sorted({r["week"] for r in receipts})[-weeks:]
    weekly_receipts: Counter[tuple[str, str]] = Counter()
    weekly_savings: defaultdict[tuple[str, str], float] = defaultdict(float)
    weekly_markdown: Counter[tuple[str, str]] = Counter()
    for receipt in receipts:
        if receipt["week"] in selected_weeks:
            key = (receipt["family_id"], receipt["week"])
            weekly_receipts[key] += 1
            weekly_savings[key] += float(receipt["savings_rub"])
    for item in items:
        week = receipt_week.get(item["receipt_id"])
        if week in selected_weeks and item["is_markdown"] == "true":
            weekly_markdown[(receipt_family[item["receipt_id"]], week)] += 1

    rng = random.Random(seed + 1000)
    heights_rows = []
    total_points: Counter[str] = Counter()
    saved_by_type: Counter[str] = Counter()
    for profile in profiles:
        family_id = profile["family_id"]
        current_growth = 0.0
        behaviour = inferred.get(family_id, "хозяин")
        completion_p = {"хозяин": 0.50, "охотник": 0.30, "категорийный": 0.35}[behaviour]
        for week in selected_weeks:
            key = (family_id, week)
            complete = rng.random() < completion_p and weekly_receipts[key] > 0
            delta = growth(weekly_receipts[key], complete, weekly_markdown[key])
            earned = points(weekly_savings[key], weekly_markdown[key], complete)
            current_growth += delta
            total_points[family_id] += earned
            saved_by_type[behaviour] += weekly_markdown[key]
            heights_rows.append({
                "family_id": family_id,
                "week": week,
                "visits": weekly_receipts[key],
                "challenge_completed": str(complete).lower(),
                "growth_delta_cm": f"{delta:.2f}",
                "growth_total_cm": f"{current_growth:.2f}",
                "points": earned,
            })
    with (out_dir / "heights.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(heights_rows[0]))
        writer.writeheader()
        writer.writerows(heights_rows)

    profile_by_id = {p["family_id"]: p for p in profiles}
    league_rows = []
    league_id = 0
    for chunk in _league_chunks(profiles):
        league_id += 1
        ranked = sorted(chunk, key=lambda p: total_points[p["family_id"]], reverse=True)
        top3_score = total_points[ranked[min(2, len(ranked) - 1)]["family_id"]]
        for rank, profile in enumerate(ranked, start=1):
            family_id = profile["family_id"]
            gap_points = max(0, top3_score - total_points[family_id] + (1 if rank > 3 else 0))
            gap_rub = round(gap_points / 0.20, 2)
            league_rows.append({
                "family_id": family_id,
                "league_id": f"league_{league_id:03d}",
                "members": len(ranked),
                "rank": rank,
                "points": total_points[family_id],
                "gap_to_top3_points": gap_points,
                "estimated_purchase_rub": gap_rub,
                "one_purchase_enough": str(gap_rub <= float(profile["avg_check_rub"])).lower(),
            })
    with (out_dir / "leagues.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(league_rows[0]))
        writer.writeheader()
        writer.writerows(league_rows)

    fraud_rows = []
    for index, profile in enumerate(profiles):
        suspicious = index > 1 and index % 173 == 0
        signals = {
            "linked_families": 5 if suspicious else 1,
            "refund_ratio": 0.65 if suspicious else round(rng.random() * 0.08, 3),
            "repetitive_markdown": suspicious,
            "referrals_24h": 0,
            "employee_pattern": False,
        }
        score, reasons = fraud_score(signals)
        fraud_rows.append({
            "family_id": profile["family_id"],
            "score": score,
            "review_required": str(review_required(score)).lower(),
            "reasons": "; ".join(reasons),
        })
    with (out_dir / "fraud.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fraud_rows[0]))
        writer.writeheader()
        writer.writerows(fraud_rows)

    closable = sum(row["one_purchase_enough"] == "true" for row in league_rows) / len(league_rows)
    flagged = sum(row["review_required"] == "true" for row in fraud_rows) / len(fraud_rows)
    final_growth = {
        row["family_id"]: float(row["growth_total_cm"])
        for row in heights_rows if row["week"] == selected_weeks[-1]
    }
    growth_bins = {
        "0–10 см": sum(v < 10 for v in final_growth.values()),
        "10–20 см": sum(10 <= v < 20 for v in final_growth.values()),
        "20–30 см": sum(20 <= v < 30 for v in final_growth.values()),
        "30+ см": sum(v >= 30 for v in final_growth.values()),
    }
    _write_svg(out_dir / "growth_distribution.svg", "Рост семей за 8 недель", growth_bins, "")
    _write_svg(out_dir / "gap_to_top3.svg", "До топ-3 достаточно одной средней покупки", {"доля семей": closable * 100}, "%")
    _write_svg(out_dir / "saved_by_type.svg", "Уценённые товары по типу поведения", dict(saved_by_type), "")

    demos = {}
    for family_id in ["family_ivanovy", "family_dima"]:
        league = next(row for row in league_rows if row["family_id"] == family_id)
        demos[family_id] = {
            "growth_cm": final_growth[family_id],
            "rank": league["rank"],
            "members": league["members"],
            "gap_purchase_rub": league["estimated_purchase_rub"],
            "points": league["points"],
        }
    summary = {
        "families": len(profiles),
        "weeks": len(selected_weeks),
        "one_purchase_to_top3_share": round(closable, 4),
        "fraud_review_share": round(flagged, 4),
        "saved_products": sum(saved_by_type.values()),
        "demos": demos,
        "note": "Синтетическая симуляция без заложенного uplift частоты.",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
