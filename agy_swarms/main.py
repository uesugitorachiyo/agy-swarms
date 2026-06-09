"""Console entrypoint for agy-swarms."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Run the agy-swarms CLI."""
    from agy_swarms.cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
