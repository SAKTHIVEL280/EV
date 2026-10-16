"""Loopback WebSocket server for the Rust app (docs/ARCHITECTURE.md §2, §6).

- Binds 127.0.0.1 on a random port.
- Opening handshake requires ``Authorization: Bearer <token>`` (constant-time
  compare) and no ``Origin`` header (browsers always send one).
- One authenticated client at a time.
- The first message must be ``hello``; everything else is refused until then.
"""

import hmac
import logging
from collections.abc import Callable
from enum import StrEnum
from http import HTTPStatus
from typing import Final

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosedError
from websockets.http11 import Request, Response

from ev_core import protocol
from ev_core.errors import StartupError
from ev_core.modules import ModuleStatus

logger = logging.getLogger(__name__)

HOST: Final = "127.0.0.1"
MAX_MESSAGE_BYTES: Final = 1024 * 1024


class ErrorCode(StrEnum):
    BAD_MESSAGE = "bad_message"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    HANDSHAKE_REQUIRED = "handshake_required"
    UNEXPECTED_MESSAGE = "unexpected_message"


MISMATCH_TEXT: Final = "EV needs to be reinstalled. Its parts are out of sync."
BAD_MESSAGE_TEXT: Final = "EV received a message it doesn't understand."
INTERNAL_ORDER_TEXT: Final = "EV's parts are talking out of order."


class CoreServer:
    def __init__(
        self,
        *,
        token: str,
        core_version: str,
        module_statuses: Callable[[], list[ModuleStatus]],
        on_shutdown: Callable[[protocol.Reason], None],
    ) -> None:
        self._expected_auth = f"Bearer {token}".encode()
        self._core_version = core_version
        self._module_statuses = module_statuses
        self._on_shutdown = on_shutdown
        self._server: Server | None = None
        self._active: ServerConnection | None = None

    async def start(self) -> int:
        """Start listening; returns the bound port."""
        self._server = await serve(
            self._handle,
            HOST,
            0,
            process_request=self._process_request,
            max_size=MAX_MESSAGE_BYTES,
            compression=None,
            # Liveness is the app-level ping/pong (ARCHITECTURE.md §2).
            ping_interval=None,
        )
        for sock in self._server.sockets:
            host, port = sock.getsockname()[:2]
            if host == HOST:
                return int(port)
        raise StartupError("EV couldn't start its core.", "server has no 127.0.0.1 socket")

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    def _process_request(self, connection: ServerConnection, request: Request) -> Response | None:
        if "Origin" in request.headers:
            logger.warning("rejected connection with Origin header")
            return connection.respond(HTTPStatus.FORBIDDEN, "Forbidden\n")
        given = request.headers.get("Authorization", "").encode()
        if not hmac.compare_digest(given, self._expected_auth):
            logger.warning("rejected connection with bad token")
            return connection.respond(HTTPStatus.UNAUTHORIZED, "Unauthorized\n")
        if self._active is not None:
            logger.warning("rejected second connection")
            return connection.respond(HTTPStatus.CONFLICT, "Conflict\n")
        return None

    async def _handle(self, connection: ServerConnection) -> None:
        # Two handshakes can pass _process_request before either handler runs.
        if self._active is not None:
            await connection.close(1008, "another client is connected")
            return
        self._active = connection
        logger.info("client connected")
        try:
            await self._session(connection)
        except ConnectionClosedError as exc:
            logger.info("client disconnected abnormally", extra={"fields": {"code": exc.code}})
        finally:
            self._active = None
            logger.info("client disconnected")

    async def _session(self, connection: ServerConnection) -> None:
        greeted = False
        async for frame in connection:
            try:
                message = protocol.decode(frame)
            except protocol.DecodeError as exc:
                logger.warning("bad message", extra={"fields": {"detail": exc.detail}})
                await self._send_error(
                    connection, ErrorCode.BAD_MESSAGE, BAD_MESSAGE_TEXT, exc.detail, exc.reply_to
                )
                continue

            if message.v != protocol.PROTOCOL_VERSION:
                await self._mismatch(connection, message.v, message.id)
                return

            match message:
                case protocol.HelloMessage():
                    if greeted:
                        await self._send_error(
                            connection,
                            ErrorCode.UNEXPECTED_MESSAGE,
                            INTERNAL_ORDER_TEXT,
                            "duplicate hello",
                            message.id,
                        )
                        continue
                    if message.payload.protocol != protocol.PROTOCOL_VERSION:
                        await self._mismatch(connection, message.payload.protocol, message.id)
                        return
                    greeted = True
                    logger.info(
                        "hello", extra={"fields": {"app_version": message.payload.app_version}}
                    )
                    await connection.send(protocol.encode(self._hello_ack(message.id)))
                case _ if not greeted:
                    await self._send_error(
                        connection,
                        ErrorCode.HANDSHAKE_REQUIRED,
                        INTERNAL_ORDER_TEXT,
                        f"{message.type} before hello",
                        message.id,
                    )
                case protocol.PingMessage():
                    await connection.send(protocol.encode(protocol.pong(message.id)))
                case protocol.ShutdownMessage():
                    logger.info(
                        "shutdown requested",
                        extra={"fields": {"reason": message.payload.reason.value}},
                    )
                    self._on_shutdown(message.payload.reason)
                    return
                case protocol.ErrorMessage():
                    logger.warning(
                        "app reported error", extra={"fields": {"code": message.payload.code}}
                    )
                    logger.debug(
                        "app error detail", extra={"fields": {"detail": message.payload.detail}}
                    )
                case protocol.HelloAckMessage() | protocol.PongMessage():
                    await self._send_error(
                        connection,
                        ErrorCode.UNEXPECTED_MESSAGE,
                        INTERNAL_ORDER_TEXT,
                        f"{message.type} is core -> app only",
                        message.id,
                    )

    def _hello_ack(self, reply_to: str) -> protocol.HelloAckMessage:
        modules = [
            protocol.ModuleStatus(
                name=s.name, state=protocol.ModuleState(s.state.value), detail=s.detail
            )
            for s in self._module_statuses()
        ]
        return protocol.hello_ack(reply_to, self._core_version, modules)

    async def _mismatch(self, connection: ServerConnection, theirs: int, reply_to: str) -> None:
        detail = f"app protocol {theirs}, core protocol {protocol.PROTOCOL_VERSION}"
        logger.error("protocol mismatch", extra={"fields": {"detail": detail}})
        await self._send_error(
            connection, ErrorCode.PROTOCOL_MISMATCH, MISMATCH_TEXT, detail, reply_to
        )
        await connection.close(1002, "protocol mismatch")

    @staticmethod
    async def _send_error(
        connection: ServerConnection,
        code: ErrorCode,
        text: str,
        detail: str | None,
        reply_to: str | None,
    ) -> None:
        # Pydantic error text can be long; the schema caps detail at 4000 chars.
        trimmed = detail[:4000] if detail is not None else None
        await connection.send(protocol.encode(protocol.error(code.value, text, trimmed, reply_to)))
