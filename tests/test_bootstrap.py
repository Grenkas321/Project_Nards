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
    """The bootstrap entry point should create and start the application."""

    class DummyController:
        def __init__(self) -> None:
            self.started = False
            self.running = False  # exit the loop immediately

        def start(self) -> None:
            self.started = True

        def handle_event(self, event) -> None:
            pass

        def update(self, dt_ms: int) -> None:
            pass

        def draw(self, surface) -> None:
            pass

    controller = DummyController()

    def _build_application(
        locale_code: str = "en",
        server_mode: bool = False,
        join_mode: bool = False,
        socket_host: str | None = None,
        socket_port: int = 8765,
    ) -> DummyController:
        assert locale_code == "ru"
        assert server_mode is False
        assert join_mode is False
        if socket_host is not None:
            assert socket_host == "127.0.0.1"
        assert socket_port == 8765
        return controller

    monkeypatch.setattr(
        "nardy.app.bootstrap.build_application",
        _build_application,
    )

    assert main(["--locale", "ru"]) == 0
    assert controller.started is True


def test_build_application_rejects_conflicting_modes() -> None:
    """Server and join modes cannot be enabled together."""
    with pytest.raises(RuntimeError, match="either --server or --join"):
        build_application(server_mode=True, join_mode=True)


def test_build_application_server_mode_wires_remote_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server mode should start local server and control white player."""

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


def test_build_application_local_mode_uses_default_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local mode should construct localizer and default engine."""

    class DummyLocalizer:
        """Capture locale selection."""

        def __init__(self, locale_code: str = "en") -> None:
            self.locale_code = locale_code

    class DummyEngine:
        """Minimal local engine placeholder."""

    class DummyController:
        """Capture constructor args from local mode."""

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    engine = DummyEngine()
    monkeypatch.setattr("nardy.i18n.Localizer", DummyLocalizer)
    monkeypatch.setattr("nardy.app.controller.AppController", DummyController)
    monkeypatch.setattr(
        "nardy.domain.engine.build_default_engine",
        lambda: engine,
    )

    app = build_application(locale_code="ru")

    assert app.kwargs["engine"] is engine
    assert app.kwargs["localizer"].locale_code == "ru"


def test_main_reports_application_build_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Main should convert bootstrap errors into exit code 1."""

    def _raise_error(**_kwargs):
        raise RuntimeError("bad mode")

    monkeypatch.setattr("nardy.app.bootstrap.build_application", _raise_error)

    assert main([]) == 1
    assert "bad mode" in capsys.readouterr().out
