from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai import evaluate, run_agent
from data import generate, prepare_target_dataset
from proto import build
from sim import simulate


def main() -> None:
    parser = argparse.ArgumentParser(description="X5 «Растём вместе» end-to-end PoC")
    parser.add_argument("--families", type=int, default=500)
    parser.add_argument("--weeks", type=int, default=8)
    parser.add_argument("--agent-sample", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--step", choices=["all", "data", "ai", "eval", "sim", "proto"], default="all")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    summary: dict[str, object] = {"config": vars(args)}

    if args.step in {"all", "data"}:
        summary["data"] = generate(args.families, args.seed, 12, root)
        summary["target_data"] = prepare_target_dataset(root)
        print(f"DATA families={summary['data']['families']} receipts={summary['data']['receipts']} seed={args.seed}")
        print(
            f"TARGET profiles={summary['target_data']['counts']['profiles']} "
            f"receipts={summary['target_data']['counts']['receipts']} "
            f"quality={summary['target_data']['status']}"
        )
    if args.step in {"all", "ai"}:
        summary["ai"] = run_agent(args.agent_sample, args.seed, root)
        print(f"AI sample={summary['ai']['sample']} mechanics={summary['ai']['mechanics']}")
    if args.step in {"all", "eval"}:
        summary["eval"] = evaluate(root)
        print(
            f"EVAL personalized={summary['eval']['personalized_behavior_accuracy']:.1%} "
            f"baseline={summary['eval']['static_one_size_fits_all_accuracy']:.1%}"
        )
    if args.step in {"all", "sim"}:
        summary["simulation"] = simulate(args.weeks, args.seed, root)
        print(
            f"SIM families={summary['simulation']['families']} "
            f"one_purchase_to_top3={summary['simulation']['one_purchase_to_top3_share']:.1%} "
            f"fraud_review={summary['simulation']['fraud_review_share']:.1%}"
        )
    if args.step in {"all", "proto"}:
        summary["prototype"] = build(root)
        print(f"PROTO path={summary['prototype']['prototype']}")

    results_dir = root / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
