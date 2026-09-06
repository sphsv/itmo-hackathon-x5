from __future__ import annotations
import argparse
import json
from pathlib import Path
from ai.evaluate import evaluate
from ai.personalizer import run_agent
from ai.review import prepare_review
from data import generate, prepare_blind_review_sample, prepare_fraud_benchmark, prepare_target_dataset, validate_source_dataset
from proto import build
from sim.simulate import simulate

def main():
    parser = argparse.ArgumentParser(description="X5 final hackathon pipeline, synthetic data only")
    parser.add_argument("--families", type=int, default=2000)
    parser.add_argument("--weeks", type=int, default=4, help="1..4 held-out replay weeks, after 8 history weeks")
    parser.add_argument("--agent-sample", type=int, default=40, help="Human review packet size; model covers ALL target profiles")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--step", choices=["all", "data", "ai", "eval", "sim", "proto"], default="all")
    args = parser.parse_args()
    if args.families < 2 or args.agent_sample < 1 or not 1 <= args.weeks <= 4:
        parser.error("families >= 2; agent-sample >= 1; weeks in 1..4")
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    summary = {"config": {**vars(args), "output_dir": "."}, "status": "synthetic"}
    if args.step in {"all", "data"}:
        summary["data"] = generate(args.families, args.seed, 12, root)
        summary["data_quality"] = validate_source_dataset(root)
        if summary["data_quality"]["status"] == "failed":
            raise RuntimeError("Structural data validation failed")
        summary["target_data"] = prepare_target_dataset(root)
        if summary["target_data"]["status"] != "passed":
            raise RuntimeError("Target dataset validation failed")
        summary["blind_review_data"] = prepare_blind_review_sample(args.agent_sample, seed=args.seed, root=root)
        summary["fraud_benchmark"] = prepare_fraud_benchmark(root)
        print("DATA", summary["data"], "QUALITY", summary["data_quality"]["status"])
    if args.step in {"all", "ai"}:
        summary["ai"] = run_agent(args.agent_sample, args.seed, root)
        summary["review"] = prepare_review(root, args.seed)
        print("MODEL", summary["ai"], "REVIEW", summary["review"])
    if args.step in {"all", "eval"}:
        summary["eval"] = evaluate(root)
        print("EVAL", summary["eval"])
    if args.step in {"all", "sim"}:
        summary["simulation"] = simulate(args.weeks, args.seed, root)
        print("REPLAY", summary["simulation"]["families"], "families")
    if args.step in {"all", "proto"}:
        summary["prototype"] = build(root)
        summary["prototype"]["prototype"] = "proto/index.html"
        print("DEMO", summary["prototype"])
    out = root / "results"
    out.mkdir(parents=True, exist_ok=True)
    name = "run_summary.json" if args.step == "all" else f"run_{args.step}.json"
    (out / name).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    # Partial runs must not leave an apparently current full-run summary.
    if args.step != "all" and (out / "run_summary.json").exists():
        previous = json.loads((out / "run_summary.json").read_text())
        previous["stale_after_partial_run"] = args.step
        (out / "run_summary.json").write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
