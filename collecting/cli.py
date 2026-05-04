from __future__ import annotations

import argparse

from collecting.runner import run_sync


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--site",
        type=str,
        default=None,
        help="Collect only selected site, for example: burdastyle",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of products for test run",
    )

    args = parser.parse_args()

    run_sync(site=args.site, limit=args.limit)


if __name__ == "__main__":
    main()