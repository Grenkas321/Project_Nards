"""Application bootstrap helpers."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from nardy import __version__
from nardy.domain.models import Player
from nardy.net import DEFAULT_HOST, DEFAULT_PORT, MatchServer, RemoteEngineProxy

if TYPE_CHECKING:
    from nardy.app.controller import AppController


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
    parser.add_argument(
        "--server",
        action="store_true",
        help="Start a local socket server and join as the white player.",
    )
    parser.add_argument(
        "--join",
        action="store_true",
        help="Join an existing socket match server as a remote client.",
    )
    parser.add_argument(
        "--socket-host",
        default=DEFAULT_HOST,
        help="Socket match host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--socket-port",
        type=int,
        default=DEFAULT_PORT,
        help="Socket match port (default: 8765).",
    )
    return parser


def build_application(
    locale_code: str = "en",
    server_mode: bool = False,
    join_mode: bool = False,
    socket_host: str = DEFAULT_HOST,
    socket_port: int = DEFAULT_PORT,
) -> AppController:
    """Create the default application controller and its dependencies."""
    from nardy.app.controller import AppController
    from nardy.domain.engine import build_default_engine
    from nardy.i18n import Localizer
    from nardy.ui.shell import ApplicationShell

    if server_mode and join_mode:
        raise RuntimeError("Use either --server or --join, not both.")

    shell = ApplicationShell()
    localizer = Localizer(locale_code=locale_code)
    if server_mode:
        server = MatchServer(host=socket_host, port=socket_port)
        server.start_in_background()
        engine = RemoteEngineProxy(host=socket_host, port=socket_port)
        return AppController(
            shell=shell,
            engine=engine,
            localizer=localizer,
            controlled_player=Player.WHITE,
            state_waiter=engine.wait_for_update,
        )
    if join_mode:
        engine = RemoteEngineProxy(host=socket_host, port=socket_port)
        return AppController(
            shell=shell,
            engine=engine,
            localizer=localizer,
            controlled_player=engine.player,
            state_waiter=engine.wait_for_update,
        )

    engine = build_default_engine()
    return AppController(shell=shell, engine=engine, localizer=localizer)


def main(argv: list[str] | None = None) -> int:
    """Console entry point used by the project script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    application = build_application(
        locale_code=args.locale,
        server_mode=args.server,
        join_mode=args.join,
        socket_host=args.socket_host,
        socket_port=args.socket_port,
    )
    application.run()
    return 0
