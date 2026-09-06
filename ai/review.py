"""A/B blinded packets and honest aggregation of human ratings."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from statistics import mean

from data.blind_review import RATING_FIELDS
from .policy import Dataset, next_week, read_csv, recommend_goal

DIMENSIONS = ("relevance", "feasibility", "clarity", "usefulness", "safety")


def prepare_review(root=Path("."), seed=42):
    root = Path(root)
    data = Dataset(root)
    week = next_week(data.weeks[-1])
    selected = read_csv(root / "data/out/blind_review_key.csv")
    public = root / "review" / "public"
    public.mkdir(parents=True, exist_ok=True)
    key, cards = [], []
    for row in selected:
        fid, rid = row["family_id"], row["review_id"]
        feature = data.features(fid, week)
        personalized = recommend_goal(feature, data.profiles[fid], week, consent=True)
        static = recommend_goal(feature, data.profiles[fid], week, consent=True, baseline=True)
        swap = int(hashlib.sha256(f"{seed}:{rid}".encode()).hexdigest()[:8], 16) % 2
        options = [personalized, static] if not swap else [static, personalized]
        key.append({"review_id": rid, "family_id": fid,
                    "personalized_option": "B" if swap else "A"})
        cats = sorted(feature["category_counts"], key=lambda c: -feature["category_counts"][c])[:5]
        cards += [f"## {rid}", "",
                  "Синтетический сценарий: взрослый планирует обычную семейную закупку, хочет видеть экономию без лишних покупок. Согласие задано для стенда.",
                  f"За 8 недель {feature['visits']} чеков; частые разрешённые категории: {', '.join(cats)}.",
                  "История категорий (число недель / суммарная экономия по ним):"]
        for cat in cats:
            saving = sum(feature["weekly_saving_minor"].get(cat, {}).values()) / 100
            cards.append(f"- {cat}: {feature['category_weeks'].get(cat, 0)} недель / {saving:.2f} ₽")
        for letter, option in zip("AB", options):
            # Same surface and explanation format to avoid identifying the method.
            text = option.get("title", "Пока не назначаем цель: недостаточно истории повторяющейся экономии.")
            cards += ["", f"### Вариант {letter}", "", text,
                      "Если цель назначена и выполнена за неделю — 25 демонстрационных баллов; дополнительные покупки не нужны.",
                      "Уценка зависит от наличия в магазине. Можно пропустить цель без штрафа."]
        cards += ["", "Отдельная гипотеза: тот же результат можно показывать как общий рост семьи. Оцените добавочную ценность такого отображения отдельно от качества цели.", ""]
    rubric = """# Инструкция оценщику

Это синтетические покупательские ситуации, не интервью. Получите только этот ZIP, не внутренние ключи и не репозиторий. Порядок A/B скрыт, но тексты могут косвенно выдавать метод: полная слепота не гарантирована.

Заполните свой assessor_id и по одной строке на review_id. Оценка 1 — плохо, 3 — приемлемо, 5 — хорошо:

- relevance: соответствует обычной закупке и наблюдаемым категориям;
- feasibility: реалистично без увеличения корзины; наличие будущих скидок неизвестно;
- clarity: понятно, что засчитается, когда и за какую награду;
- usefulness: помогает контролировать бюджет;
- safety: нет давления на дополнительные покупки и стимулирования исключённых категорий.

preferred_option: A, B или neither. family_added_value_1_5 оценивается отдельно; это мнение оценщика, не доказательство эффекта семьи. Для отказа от назначения оценивайте уместность отказа, а не воображаемую цель.

Не угадывайте будущие чеки. Все провалы безопасности и низкие оценки объясните в comment. Нужно минимум два независимых оценщика на каждый пример. Автор модели может проверить пакет, но не считается независимым оценщиком. Не согласовывайте оценки между собой до сдачи.
"""
    (public / "cases.md").write_text("\n".join(cards), encoding="utf-8")
    (public / "README.md").write_text(rubric, encoding="utf-8")
    fields = RATING_FIELDS + ["family_added_value_1_5"]
    with (public / "ratings_template.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({"review_id": r["review_id"]} for r in key)
    internal = root / "results" / "review_key.json"
    internal.parent.mkdir(parents=True, exist_ok=True)
    internal.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(root / "review" / "reviewer_packet.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("README.md", "cases.md", "ratings_template.csv"):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 6, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (public / name).read_bytes())
    return {"cases": len(key), "human_ratings": "not_collected",
            "reviewer_packet": "review/reviewer_packet.zip", "internal_key": "results/review_key.json"}


def aggregate_ratings(root, paths):
    root = Path(root)
    key = {r["review_id"]: r for r in json.loads((root / "results/review_key.json").read_text())}
    values, seen, counts, failures = defaultdict(list), set(), defaultdict(set), []
    preferred, family = defaultdict(int), []
    for path in paths:
        for row in read_csv(Path(path)):
            if not row.get("assessor_id", "").strip():
                if any(row.get(f"option_{option}_{dimension}_1_5", "").strip()
                       for option in "ab" for dimension in DIMENSIONS):
                    raise ValueError("Ratings without assessor_id")
                continue
            rid, assessor = row["review_id"], row["assessor_id"].strip()
            if rid not in key or (rid, assessor) in seen:
                raise ValueError("Unknown or duplicate assessor/review pair")
            seen.add((rid, assessor))
            counts[rid].add(assessor)
            for option in "ab":
                method = "personalized" if option.upper() == key[rid]["personalized_option"] else "static"
                for dimension in DIMENSIONS:
                    score = int(row[f"option_{option}_{dimension}_1_5"])
                    if score not in range(1, 6):
                        raise ValueError("Ratings must be integers 1..5")
                    values[f"{method}_{dimension}"].append(score)
                    if score <= 2:
                        failures.append({"review_id": rid, "assessor_id": assessor,
                                         "method": method, "dimension": dimension,
                                         "score": score, "comment": row.get("comment", "")})
            choice = row["preferred_option"]
            if choice not in {"A", "B", "neither"}:
                raise ValueError("preferred_option must be A, B or neither")
            preferred["neither" if choice == "neither" else
                      "personalized" if choice == key[rid]["personalized_option"] else "static"] += 1
            if row.get("family_added_value_1_5", ""):
                score = int(row["family_added_value_1_5"])
                if score not in range(1, 6):
                    raise ValueError("Family score must be 1..5")
                family.append(score)
    complete = bool(key) and all(len(counts[rid]) >= 2 for rid in key)
    return {"status": "complete" if complete else "partial" if seen else "not_measured",
            "rated_pairs": len(seen), "cases": len(key),
            "cases_with_two_assessors": sum(len(counts[rid]) >= 2 for rid in key),
            "means": {k: round(mean(v), 3) for k, v in sorted(values.items())},
            "preferred_counts": dict(preferred), "low_ratings": failures,
            "family_added_value_mean": round(mean(family), 3) if family else None,
            "note": "Human judgment on synthetic episodes, not customer research or uplift. Independence is a process requirement, not verified by assessor_id."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("ratings", nargs="+")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    report = aggregate_ratings(args.root, args.ratings)
    (args.root / "results/human_review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
