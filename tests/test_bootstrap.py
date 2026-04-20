"""Tests for the package bootstrap helpers."""

from __future__ import annotations

from nardy.app.bootstrap import build_parser, main


def test_parser_accepts_version_flag() -> None:
    """The parser should expose the version option."""
    parser = build_parser()
    version_action = next(
        action
        for action in parser._actions
        if "--version" in action.option_strings
    )
    assert version_action is not None


def test_main_returns_success_for_default_arguments() -> None:
    """The bootstrap entry point should succeed without arguments."""
    assert main([]) == 0
