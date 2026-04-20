"""Application bootstrap helpers."""

from __future__ import annotations

import argparse

from nardy import __version__
from nardy.app.controller import AppController
from nardy.domain.engine import build_default_engine
from nardy.i18n import Localizer
from nardy.ui.shell import ApplicationShell


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="nardy",
        description="Run the Nardy application.",
    )
    parser.add_argument(
        "--locale",
        choices=("en", "ru"),
        default="en",
        help="Set the UI locale for the current session.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def build_application(locale_code: str = "en") -> AppController:
    """Create the default application controller and its dependencies."""
    shell = ApplicationShell()
    engine = build_default_engine()
    localizer = Localizer(locale_code=locale_code)
    return AppController(shell=shell, engine=engine, localizer=localizer)


def main(argv: list[str] | None = None) -> int:
    """Console entry point used by the project script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    application = build_application(locale_code=args.locale)
    application.run()
    return 0
