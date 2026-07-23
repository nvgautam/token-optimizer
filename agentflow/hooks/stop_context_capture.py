"""Stop hook stub — no-op, allows session stop to proceed."""
import sys

FILL_STALE_SECONDS = 60


def main() -> None:
    sys.exit(0)


if __name__ == "__main__":
    main()
