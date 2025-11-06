"""Entrypoint for ``python -m apollo_gatherer``."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())


