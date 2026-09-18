#!/usr/bin/env python3
"""Run the minimal SDOC solution against the participant bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.pipeline import process_inbox, validate_submission
from src.service import load_inbox_class, write_json


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_BUNDLE = PROJECT_ROOT.parent / "sdoc-hackathon-bundle"
DEFAULT_OUTPUT = PROJECT_ROOT / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify the inbox and compare plain-text SI/BL pairs.")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE, help="Participant bundle directory")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="Directory for JSON results")
    parser.add_argument(
        "--submit-url",
        help="Optional official local self-evaluation URL, for example http://localhost:8080",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = args.bundle.resolve()
    output_dir = args.output_dir.resolve()
    Inbox = load_inbox_class(bundle)
    inbox = Inbox(str(bundle))

    submission, internal_results, summary = process_inbox(inbox)
    validate_submission(submission, inbox.sample_submission())

    write_json(output_dir / "submission.json", submission)
    write_json(output_dir / "results.json", internal_results)
    if args.submit_url:
        score = Inbox(args.submit_url).submit(submission)
        write_json(output_dir / "self_evaluation.json", score)
        summary["self_evaluation"] = score
    write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
