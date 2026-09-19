#!/usr/bin/env python3
"""Run the minimal SDOC solution against the participant bundle."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

from src.pipeline import process_inbox, validate_submission


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PROJECT_ROOT / "output"


def find_default_bundle() -> Path:
    """Prefer the bundle shipped with this repo, while supporting the old layout."""
    candidates = (
        PROJECT_ROOT / "local-data" / "participant-bundle",
        PROJECT_ROOT.parent / "sdoc-hackathon-bundle",
    )
    return next((path for path in candidates if (path / "loader.py").is_file()), candidates[0])


DEFAULT_BUNDLE = find_default_bundle()


def load_inbox_class(bundle: Path) -> type[Any]:
    loader_path = bundle / "loader.py"
    if not loader_path.is_file():
        raise FileNotFoundError(
            f"Participant bundle not found at {bundle}. "
            "Pass its location with --bundle, or place it at "
            f"{PROJECT_ROOT / 'local-data' / 'participant-bundle'}."
        )
    spec = importlib.util.spec_from_file_location("participant_loader", loader_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load participant loader: {loader_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Inbox


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
