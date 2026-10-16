"""Entry point: ``python -m ev_core`` and the packaged ``ev-core`` executable."""

import asyncio
import os
import sys

from ev_core.app import run


def main() -> None:
    sys.exit(asyncio.run(run(os.environ, sys.stdout, sys.stdin)))


if __name__ == "__main__":
    main()
