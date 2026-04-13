import sys

from dotenv import load_dotenv

from app.logging_config import setup_logging


def _parse_log_level(argv: list[str]) -> str | None:
    i = 0
    while i < len(argv):
        if argv[i] == "--log-level" and i + 1 < len(argv):
            return argv[i + 1]
        i += 1
    return None


def bootstrap() -> None:
    load_dotenv()

    cli_log_level = _parse_log_level(sys.argv[1:])
    setup_logging(cli_log_level)


bootstrap()

from app.pipeline import main  # noqa: E402


if __name__ == "__main__":
    main()