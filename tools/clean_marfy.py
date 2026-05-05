from __future__ import annotations

import json
from pathlib import Path


BAD_PART = "the-marfy-hand-made-pre-cut-sewing-pattern"

INPUT_FILE = Path(
    r"D:\diplom\crowler\dataset\links\marfy\the-marfy-hand-made-pre-cut-sewing-pattern\products.jsonl"
)


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"File not found: {INPUT_FILE}")

    backup_file = INPUT_FILE.with_suffix(INPUT_FILE.suffix + ".bak")
    backup_file.write_text(INPUT_FILE.read_text(encoding="utf-8"), encoding="utf-8")

    kept: list[str] = []
    removed = 0

    with INPUT_FILE.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Bad JSON at line {line_no}: {e}") from e

            url = str(row.get("url", ""))

            if BAD_PART in url or "#" in url:
                removed += 1
                continue

            kept.append(json.dumps(row, ensure_ascii=False))

    INPUT_FILE.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    print(f"Done: {INPUT_FILE}")
    print(f"Backup: {backup_file}")
    print(f"Kept: {len(kept)}")
    print(f"Removed: {removed}")


if __name__ == "__main__":
    main()