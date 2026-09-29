"""Validate a local read-only state snapshot without network or authority writes."""
import argparse
import json
from pathlib import Path

from medical_learning_system.project_health import validate_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--max-age-hours", type=float, default=24)
    args = parser.parse_args()
    try:
        result = validate_snapshot(
            json.loads(args.snapshot.read_text()), max_age_hours=args.max_age_hours
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"REVIEW_REQUIRED: {error}\n")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
