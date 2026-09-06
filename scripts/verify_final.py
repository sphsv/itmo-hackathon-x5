"""Reproduce all generated artifacts twice in temporary directories; record hashes."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                           cwd=ROOT, capture_output=True, text=True)
    if tests.returncode:
        print(tests.stdout + tests.stderr)
        raise SystemExit(tests.returncode)
    with tempfile.TemporaryDirectory(prefix="x5-final-a-") as first, tempfile.TemporaryDirectory(prefix="x5-final-b-") as second:
        outputs = [Path(first), Path(second)]
        for output in outputs:
            subprocess.run([sys.executable, "run_demo.py", "--families", "2000", "--weeks", "4",
                            "--agent-sample", "40", "--seed", "42", "--output-dir", str(output)],
                           cwd=ROOT, check=True, capture_output=True, text=True)
        files = sorted(p.relative_to(outputs[0]) for p in outputs[0].rglob("*") if p.is_file())
        assert files == sorted(p.relative_to(outputs[1]) for p in outputs[1].rglob("*") if p.is_file())
        hashes = {}
        for relative in files:
            first_hash, second_hash = (fingerprint(root / relative) for root in outputs)
            if first_hash != second_hash:
                raise AssertionError(f"Non-reproducible artifact: {relative}")
            hashes[str(relative)] = first_hash
        # Compare checked-in/current outputs as well, rather than merely two fresh runs.
        mismatch = [str(relative) for relative in files
                    if not (ROOT / relative).exists() or fingerprint(ROOT / relative) != hashes[str(relative)]]
        if mismatch:
            raise AssertionError(f"Workspace outputs need regeneration: {mismatch}")
        report = {"status": "passed", "command": "python3 scripts/verify_final.py",
                  "runs": 2, "seed": 42, "families": 2000, "matched_artifacts": len(files),
                  "workspace_matches_clean_runs": True,
                  "test_output": tests.stdout + tests.stderr, "sha256": hashes,
                  "note": "Temporary output directories; same checked-out source and Python environment. Not a claim of a real-user pilot."}
        (ROOT / "results/verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"PASS: tests and {len(files)} byte-identical artifacts across two fresh runs and workspace")


if __name__ == "__main__":
    main()
