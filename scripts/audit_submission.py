"""Audit final submission structure, evidence and protected PR files. No external writes."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
BASE = "82b9846"
PRE_CLEANUP = "fbe14cb"
PR_HEADS = ("003a4fb524f8e951b70750cf73b526c99481124e", "076f104e9ae8b6af01b73a31b49624f238c5f5e9")
FINAL_DOCS = ("README.md", "PROJECT_DESCRIPTION.md", "PRODUCT_FINAL.md", "PRODUCT_VALIDATION.md",
              "PILOT_DESIGN.md", "MODEL_CARD.md", "DEMO.md", "ADDITIONAL_MATERIALS.md",
              "HUMAN_REVIEW.md", "FINAL_SUBMISSION_CHECKLIST.md", "ЧТО_ОСТАЛОСЬ_ДОДЕЛАТЬ.md")


def git(*args):
    return subprocess.check_output(["git", "-c", "core.quotepath=false", *args], cwd=ROOT, text=True).splitlines()


def main():
    checks = {}
    def check(name, condition):
        checks[name] = bool(condition)
    docs = {name: (ROOT / name).read_text(encoding="utf-8") for name in FINAL_DOCS}
    description = docs["PROJECT_DESCRIPTION.md"]
    annotation = description.split("## Аннотация\n", 1)[1].split("\n## ", 1)[0].strip()
    paragraphs = [p for p in annotation.split("\n\n") if p.strip()]
    words = len(annotation.split())
    check("annotation_6_or_7_paragraphs", len(paragraphs) in {6, 7})
    check("annotation_compact_for_a4", words <= 350 and len(annotation) <= 3500)
    for heading in ("Проблематика", "Постановка задачи", "Описание технического решения",
                    "Полученные результаты", "Дальнейшие планы по развитию", "Команда и распределение задач"):
        check("description_section_" + heading, "## " + heading in description)
    for name in ("Талалаев Иван Владимирович", "Тищенко Егор Валерьевич", "Сухова Софья Николаевна"):
        check("team_" + name, name in description)
    check("team_actual_participation", description.count("| Активное |") == 3)
    check("three_product_documents", all((ROOT / name).exists() for name in
          ("PRODUCT_FINAL.md", "PRODUCT_VALIDATION.md", "PILOT_DESIGN.md")))
    missing_links = []
    for name, body in docs.items():
        for target in re.findall(r"\]\(([^)]+)\)", body):
            if "://" in target or target.startswith("#"):
                continue
            target = unquote(target.split("#")[0])
            if not (ROOT / Path(name).parent / target).exists():
                # Package and this report are generated after the audit, with known destinations.
                if target not in {"submission/FINAL_SUBMISSION.zip", "results/submission_audit.json"}:
                    missing_links.append([name, target])
    check("current_document_links", not missing_links)
    summary = json.loads((ROOT / "results/run_summary.json").read_text())
    metrics = json.loads((ROOT / "ai/out/eval.json").read_text())["summary"]
    verification = json.loads((ROOT / "results/verification.json").read_text())
    browser = json.loads((ROOT / "output/demo/browser_report.json").read_text())
    check("one_run_summary_matches_eval", summary["eval"] == metrics and "stale_after_partial_run" not in summary)
    check("checked_synthetic_numbers", summary["data"]["families"] == 2000 and metrics["unique_families"] == 510
          and metrics["sample_size"] == 2040 and summary["ai"]["assigned"] == 510)
    check("test_and_reproducibility_report", verification["status"] == "passed"
          and verification["workspace_matches_clean_runs"] and "Ran 25 tests" in verification["test_output"])
    drift = [name for name, digest in verification["sha256"].items()
             if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    check("generated_evidence_has_not_drifted", not drift)
    check("browser_event_cycle", browser["status"] == "passed" and browser["earned_points"] == 28
          and browser["duplicate_points"] == 28 and browser["returned_points"] == 0)
    with ZipFile(ROOT / "output/presentation/PRESENTATION_FINAL.pptx") as archive:
        slides = []
        for index in range(1, 10):
            tree = ET.fromstring(archive.read(f"ppt/slides/slide{index}.xml"))
            slides.append(" ".join(t.text or "" for t in tree.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t")))
        check("slide_has_real_demo_receipt", archive.read("ppt/media/image.png") == (ROOT / "output/demo/06_receipt.png").read_bytes())
    check("nine_slides", len(slides) == 9)
    for system in ("personalized", "static"):
        rate = f"{metrics['systems'][system]['observed_completion_rate_itt']*100:.1f}%".replace(".", ",")
        check("slide_metric_" + system, rate in slides[5])
    check("slide_test_count", "25 тестов" in slides[5])
    check("slide_team_roles_and_participation", all(name in slides[8] for name in ("Талалаев Иван", "Тищенко Егор", "Сухова Софья"))
          and slides[8].count("активное") == 3)
    check("slide_old_metrics_removed", "96,7%" not in " ".join(slides) and "43,5%" not in " ".join(slides))
    check("final_pdf_exists", (ROOT / "output/presentation/PRESENTATION_FINAL.pdf").read_bytes().startswith(b"%PDF"))
    protected = set()
    for head in PR_HEADS:
        protected.update(git("diff", "--name-only", BASE, head))
    missing_protected = sorted(name for name in protected if not (ROOT / name).exists())
    check("all_pr_files_preserved", not missing_protected)
    original = set(git("ls-tree", "-r", "--name-only", BASE))
    deleted = git("diff", "--diff-filter=D", "--name-only", PRE_CLEANUP)
    check("deletions_only_old_main_not_pr", all(name in original and name not in protected for name in deleted))
    check("explicit_open_relevance", metrics["human_relevance"] == "not_measured"
          and "70%" in docs["ЧТО_ОСТАЛОСЬ_ДОДЕЛАТЬ.md"])
    report = {
        "status": "passed_with_declared_open_items" if all(checks.values()) else "failed",
        "deadline": "2026-09-07 10:00 (as specified by user)",
        "checks": checks, "annotation_paragraphs": len(paragraphs), "annotation_words": words,
        "annotation_characters": len(annotation),
        "a4_note": "Compact text limit, not a universal guarantee for arbitrary fonts/margins.",
        "protected_pr_files": sorted(protected), "missing_protected": missing_protected,
        "removed_old_main_files": deleted, "missing_links": missing_links, "artifact_drift": drift,
        "open_items": ["Independent human relevance >=70% not measured",
                       "Team acceptance of roles/slides and timed rehearsal",
                       "Real reward economics and business effects not established",
                       "Live league and referral workflow omitted from selected scope",
                       "Human upload to hackathon submission form"],
        "presentation_visual_check": "PDF visually reviewed separately; XML checks do not prove absence of layout clipping",
    }
    (ROOT / "results/submission_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks),
                      "failed": [name for name, ok in checks.items() if not ok],
                      "annotation_paragraphs": len(paragraphs), "annotation_words": words,
                      "protected_files": len(protected), "removed": deleted}, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
