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
        choices=("ru", "en", "hy"),
        default="ru",
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
        default=None,
        help="Socket match host (default: 127.0.0.1 for client, 0.0.0.0 for server).",
    )
    parser.add_argument(
        "--socket-port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Socket match port (default: {DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--tunnel",
        action="store_true",
        help="With --server: expose the server through a free internet tunnel "
             "and print the public address as 'TUNNEL_ADDR host:port'.",
    )
    parser.add_argument(
        "--mode",
        choices=("long", "short"),
        default=None,
        help="With --server: start this game mode immediately instead of "
             "showing the menu.",
    )
    return parser


def build_application(
    locale_code: str = "en",
    server_mode: bool = False,
    join_mode: bool = False,
    socket_host: str | None = None,
    socket_port: int = DEFAULT_PORT,
) -> AppController:
    """Create the default application controller and its dependencies."""
    from nardy.app.controller import AppController
    from nardy.domain.engine import build_default_engine
    from nardy.i18n import Localizer

    if server_mode and join_mode:
        raise RuntimeError("Use either --server or --join, not both.")

    localizer = Localizer(locale_code=locale_code)

    # Determine effective socket host
    if server_mode and socket_host is None:
        effective_host = "0.0.0.0"
    elif not server_mode and socket_host is None:
        effective_host = DEFAULT_HOST
    else:
        effective_host = socket_host

    if server_mode:
        server = MatchServer(host=effective_host, port=socket_port)
        server.start_in_background()
        engine = RemoteEngineProxy(host=DEFAULT_HOST, port=socket_port)  # client connects to localhost
        return AppController(
            engine=engine,
            localizer=localizer,
            controlled_player=Player.WHITE,
            state_waiter=engine.wait_for_update,
        )
    if join_mode:
        engine = RemoteEngineProxy(host=effective_host, port=socket_port)
        # If connection failed, engine.error will be set and methods will raise
        return AppController(
            engine=engine,
            localizer=localizer,
            controlled_player=engine.player,
            state_waiter=engine.wait_for_update,
        )

    engine = build_default_engine()
    return AppController(engine=engine, localizer=localizer)


def _pick_free_port() -> int:
    """Ask the OS for a free TCP port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv: list[str] | None = None) -> int:
    """Console entry point used by the project script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.server and args.tunnel:
        # Auto-hosted games pick a fresh free port. A fixed default port
        # would silently attach to a leftover server from a previous game
        # (Windows' SO_REUSEADDR allows rebinding a busy port), putting two
        # hosts on one match.
        args.socket_port = _pick_free_port()
    try:
        controller = build_application(
            locale_code=args.locale,
            server_mode=args.server,
            join_mode=args.join,
            socket_host=args.socket_host,
            socket_port=args.socket_port,
        )
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    if args.server and args.tunnel:
        # The tunnel must live in THIS (game-hosting) process: if it ran in
        # the menu process that spawned us, closing that window would cut
        # the opponent's connection mid-game.
        from nardy.net.tunnel import start_tunnel
        addr, error = start_tunnel(args.socket_port)
        if addr:
            print(f"TUNNEL_ADDR {addr}", flush=True)
        else:
            print(f"TUNNEL_ERROR {error}", flush=True)

    import pygame

    pygame.init()

    from nardy.ui.sounds import init_sounds
    init_sounds()

    screen = pygame.display.set_mode((1024, 720), pygame.RESIZABLE)
    pygame.display.set_caption("Взрывные нарды")
    clock = pygame.time.Clock()

    # pygame.scrap (non-Windows clipboard fallback) needs a live window —
    # must be initialized after set_mode, never before.
    try:
        pygame.scrap.init()
    except Exception:
        pass

    controller.start()
    if args.server and args.mode:
        from nardy.domain.models import GameMode
        controller.start_game(GameMode.LONG if args.mode == "long" else GameMode.SHORT)
    while controller.running:
        dt = clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                controller.close()
                break
            controller.handle_event(event)
        controller.update(dt)
        controller.draw(screen)
        pygame.display.flip()

    pygame.quit()
    return 0
