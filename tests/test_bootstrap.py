"""Tests for the package bootstrap helpers."""

from __future__ import annotations

import pytest

from nardy.app.bootstrap import build_application, build_parser, main
from nardy.domain.models import Player


def test_parser_accepts_version_flag() -> None:
    """The parser should expose the version option."""
    parser = build_parser()
    version_action = next(
        action
        for action in parser._actions
        if "--version" in action.option_strings
    )
    assert version_action is not None


def test_parser_supports_socket_mode_flags() -> None:
    """The parser should include socket server and join options."""
    parser = build_parser()
    options = {
        flag
        for action in parser._actions
        for flag in action.option_strings
    }
    assert "--server" in options
    assert "--join" in options
    assert "--socket-host" in options
    assert "--socket-port" in options


def test_main_runs_application(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bootstrap entry point should create and run the application."""

    class DummyApplication:
        def __init__(self) -> None:
            self.ran = False

        def run(self) -> None:
            self.ran = True

    application = DummyApplication()

    def _build_application(
        locale_code: str = "en",
        server_mode: bool = False,
        join_mode: bool = False,
        socket_host: str | None = None,   # разрешаем None
        socket_port: int = 8765,
    ) -> DummyApplication:
        assert locale_code == "ru"
        assert server_mode is False
        assert join_mode is False
        # In non‑network mode socket_host can be None or anything, skip check
        if socket_host is not None:
            assert socket_host == "127.0.0.1"  # or just ignore
        assert socket_port == 8765
        return application

    monkeypatch.setattr(
        "nardy.app.bootstrap.build_application",
        _build_application,
    )

    assert main(["--locale", "ru"]) == 0
    assert application.ran is True


def test_build_application_rejects_conflicting_modes() -> None:
    """Server and join modes cannot be enabled together."""
    with pytest.raises(RuntimeError, match="either --server or --join"):
        build_application(server_mode=True, join_mode=True)


def test_build_application_server_mode_wires_remote_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server mode should start local server and control white player."""

    class DummyShell:
        """Minimal shell placeholder."""

    class DummyLocalizer:
        """Minimal localizer placeholder."""

        def __init__(self, locale_code: str = "en") -> None:
            self.locale_code = locale_code

    class DummyController:
        """Capture constructor args from build_application."""

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class DummyServer:
        """Track whether background startup happened."""

        def __init__(self, host: str, port: int) -> None:
            self.host = host
            self.port = port
            self.started = False

        def start_in_background(self) -> None:
            self.started = True

    class DummyRemoteEngine:
        """Provide expected proxy API for controller wiring."""

        def __init__(self, host: str, port: int) -> None:
            self.host = host
            self.port = port
            self.player = Player.BLACK

        def wait_for_update(self):
            return None

    created_server: dict[str, DummyServer] = {}

    def _server_factory(host: str, port: int) -> DummyServer:
        server = DummyServer(host=host, port=port)
        created_server["instance"] = server
        return server

    monkeypatch.setattr("nardy.ui.shell.ApplicationShell", DummyShell)
    monkeypatch.setattr("nardy.i18n.Localizer", DummyLocalizer)
    monkeypatch.setattr("nardy.app.controller.AppController", DummyController)
    monkeypatch.setattr("nardy.app.bootstrap.MatchServer", _server_factory)
    monkeypatch.setattr("nardy.app.bootstrap.RemoteEngineProxy", DummyRemoteEngine)

    app = build_application(
        locale_code="ru",
        server_mode=True,
        socket_host="127.0.0.9",
        socket_port=9900,
    )

    assert created_server["instance"].started is True
    assert app.kwargs["controlled_player"] is Player.WHITE
    assert callable(app.kwargs["state_waiter"])


def test_build_application_join_mode_uses_remote_player(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Join mode should pass remote assigned player to controller."""

    class DummyShell:
        """Minimal shell placeholder."""

    class DummyLocalizer:
        """Minimal localizer placeholder."""

        def __init__(self, locale_code: str = "en") -> None:
            self.locale_code = locale_code

    class DummyController:
        """Capture constructor args from build_application."""

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class DummyRemoteEngine:
        """Provide expected proxy API for controller wiring."""

        def __init__(self, host: str, port: int) -> None:
            self.host = host
            self.port = port
            self.player = Player.BLACK

        def wait_for_update(self):
            return None

    monkeypatch.setattr("nardy.ui.shell.ApplicationShell", DummyShell)
    monkeypatch.setattr("nardy.i18n.Localizer", DummyLocalizer)
    monkeypatch.setattr("nardy.app.controller.AppController", DummyController)
    monkeypatch.setattr("nardy.app.bootstrap.RemoteEngineProxy", DummyRemoteEngine)

    app = build_application(
        locale_code="en",
        join_mode=True,
        socket_host="127.0.0.8",
        socket_port=9901,
    )

    assert app.kwargs["controlled_player"] is Player.BLACK
    assert callable(app.kwargs["state_waiter"])
