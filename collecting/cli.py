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

    parser.add_argument(
        "--round-robin",
        action="store_true",
        help="Interleave products from different sites",
    )

    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Process several products in parallel, but no more than MAX_PER_SITE per site",
    )

    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=None,
        help="Override MAX_CONCURRENT_PRODUCTS for this run",
    )

    args = parser.parse_args()

    run_sync(
        site=args.site,
        limit=args.limit,
        round_robin=args.round_robin,
        parallel=args.parallel,
        max_concurrent=args.max_concurrent,
    )


if __name__ == "__main__":
    main()