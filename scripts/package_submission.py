"""Package final deliverables, not the whole repository or internal review keys."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "output/presentation/PRESENTATION_FINAL.pdf", "output/presentation/PRESENTATION_FINAL.pptx",
    "PROJECT_DESCRIPTION.md", "PRODUCT_FINAL.md", "PRODUCT_VALIDATION.md", "PILOT_DESIGN.md",
    "ADDITIONAL_MATERIALS.md", "MODEL_CARD.md", "DEMO.md", "HUMAN_REVIEW.md",
    "ECONOMICS.md", "AI_LOG.md", "FINAL_SUBMISSION_CHECKLIST.md", "ЧТО_ОСТАЛОСЬ_ДОДЕЛАТЬ.md",
    "DEFENSE_SCRIPT.md", "ai/out/eval.md", "ai/out/eval.json",
    "results/run_summary.json", "results/verification.json", "results/submission_audit.json",
    "data/out/data_quality_report.json", "data/out/target_quality_report.json",
    "data/out/fraud_benchmark_report.json", "review/reviewer_packet.zip",
    "output/demo/browser_report.json",
    *[f"output/demo/{name}.png" for name in
      ("01_before", "02_completed", "03_duplicate", "04_returned", "05_mobile", "06_receipt")],
]


def main():
    audit = json.loads((ROOT / "results/submission_audit.json").read_text())
    if audit["status"] != "passed_with_declared_open_items":
        raise ValueError("Run audit_submission.py successfully first")
    out = ROOT / "submission"
    out.mkdir(exist_ok=True)
    contents = {name: (ROOT / name).read_bytes() for name in FILES}
    contents["START_HERE.md"] = """# Финальная сдача · 07.09.2026 до 10:00

1. Презентация: output/presentation/PRESENTATION_FINAL.pdf (PPTX — редактируемый исходник).
2. Описание: PROJECT_DESCRIPTION.md.
3. Продукт: PRODUCT_FINAL.md, PRODUCT_VALIDATION.md, PILOT_DESIGN.md — ровно три материала.
4. Дополнительное — рекомендуемые 6 файлов: ADDITIONAL_MATERIALS.md, MODEL_CARD.md, ai/out/eval.md, results/verification.json, output/demo/02_completed.png, output/demo/04_returned.png. Остальные файлы — запасные доказательства и инструкции, не нужно загружать их все в раздел с лимитом 10.

Загружайте файлы в соответствующие разделы; сам ZIP — удобная передача комплекта, не замена обязательных полей формы.
Код и полный воспроизводимый проект: https://github.com/sphsv/itmo-hackathon-x5
Список действий коллегам: ЧТО_ОСТАЛОСЬ_ДОДЕЛАТЬ.md. Человеческая релевантность и бизнесовый эффект пока не измерены.
Этот архив содержит документы и доказательства, не код приложения. Для запуска используйте репозиторий.
Скрытые ключи A/B, базы SQLite, личные данные оценщиков и архивные черновики сюда не включены.
""".encode()
    manifest = {"deadline": "07.09.2026 10:00", "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(contents.items())}}
    contents["MANIFEST.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    target = out / "FINAL_SUBMISSION.zip"
    with ZipFile(target, "w") as archive:
        for name, data in sorted(contents.items()):
            info = ZipInfo(name, date_time=(2026, 9, 7, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    with ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity failed")
        for name, expected in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
        assert not any("DRAFT" in name or "CHECKPOINT" in name or "review_key" in name
                       or name.endswith(".sqlite3") for name in archive.namelist())
    (out / "MANIFEST.json").write_text(json.dumps({**manifest,
        "archive_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Packaged and verified {len(contents)} files: {target.relative_to(ROOT)} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
