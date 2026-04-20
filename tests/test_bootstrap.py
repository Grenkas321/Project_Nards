"""Tests for the package bootstrap helpers."""

from __future__ import annotations

import pytest

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


def test_main_runs_application(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bootstrap entry point should create and run the application."""

    class DummyApplication:
        """Minimal stand-in for the application controller."""

        def __init__(self) -> None:
            """Initialize the dummy state."""
            self.ran = False

        def run(self) -> None:
            """Record that the application was started."""
            self.ran = True

    application = DummyApplication()

    def _build_application(locale_code: str = "en") -> DummyApplication:
        """Return the dummy application for tests."""
        assert locale_code == "ru"
        return application

    monkeypatch.setattr(
        "nardy.app.bootstrap.build_application",
        _build_application,
    )

    assert main(["--locale", "ru"]) == 0
    assert application.ran is True
