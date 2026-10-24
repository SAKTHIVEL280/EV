"""Loopback WebSocket server for the Rust app (docs/ARCHITECTURE.md §2, §6).

- Binds 127.0.0.1 on a random port.
- Opening handshake requires ``Authorization: Bearer <token>`` (constant-time
  compare) and no ``Origin`` header (browsers always send one).
- One authenticated client at a time.
- The first message must be ``hello``; everything else is refused until then.
- Chat requests become bus events; turn and model events from the bus are
  forwarded through one ordered outbox per connection.
"""

import asyncio
import contextlib
import hmac
import logging
from collections.abc import Callable
from enum import StrEnum
from http import HTTPStatus
from typing import Final

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from websockets.http11 import Request, Response

from ev_core import protocol
from ev_core.bus import Event, EventBus
from ev_core.config import EffortLevel
from ev_core.errors import StartupError
from ev_core.interfaces.events import (
    ActionRecorded,
    ActionUndone,
    ChatCancelRequested,
    ChatDelta,
    ChatDone,
    ChatFailed,
    ChatRequested,
    ChatResetRequested,
    ChatStarted,
    ChatToolChanged,
    ConfigGetRequested,
    ConfigRejected,
    ConfigResetRequested,
    ConfigSetRequested,
    ConfigStateChanged,
    ContextCaptured,
    ContextCaptureRequested,
    ContextClearRequested,
    ContextReplaced,
    ContextReplaceRequested,
    FocusModeChanged,
    LlmStatusChanged,
    ModelCancelRequested,
    ModelDownloadRequested,
    ModelsGetRequested,
    ModelsStateChanged,
    TimerFired,
    ToolAnswered,
    ToolConfirmClosed,
    ToolConfirmRequested,
    UndoRequested,
)
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


def to_message(event: Event) -> protocol.AnyMessage | None:
    """Wire message for an outbound bus event; None for events that stay in core."""
    match event:
        case ChatStarted():
            return protocol.chat_started(
                event.turn_id, protocol.Effort(event.effort.value), event.model
            )
        case ChatDelta():
            return protocol.chat_delta(event.turn_id, event.text)
        case ChatToolChanged():
            return protocol.chat_tool(
                event.turn_id, event.name, protocol.ChatToolState(event.state)
            )
        case ChatDone():
            timings = protocol.ChatTimings(
                first_token_ms=event.first_token_ms,
                total_ms=event.total_ms,
                prompt_tokens=event.prompt_tokens,
                generated_tokens=event.generated_tokens,
            )
            return protocol.chat_done(
                event.turn_id,
                event.text,
                protocol.Effort(event.effort.value),
                event.model,
                timings,
                cancelled=event.cancelled,
            )
        case ChatFailed():
            return protocol.chat_failed(event.turn_id, event.code, event.message)
        case LlmStatusChanged():
            return protocol.llm_status(protocol.LlmState(event.state), event.model, event.detail)
        case ConfigStateChanged():
            items = [
                protocol.SettingItem(
                    section=i.section,
                    key=i.key,
                    nav=protocol.SettingNav(i.nav.value),
                    label=i.label,
                    description=i.description,
                    kind=protocol.SettingKind(i.kind),
                    default=i.default,
                    value=i.value,
                    options=list(i.options) or None,
                    minimum=i.minimum,
                    maximum=i.maximum,
                    unit=i.unit,
                    widget=protocol.SettingWidget(i.widget) if i.widget else None,
                    role=protocol.SettingRole(i.role) if i.role else None,
                    steps=list(i.steps) or None,
                )
                for i in event.items
            ]
            warnings = [
                protocol.ConfigWarningItem(key=w.key, message=w.message) for w in event.warnings
            ]
            return protocol.config_state(event.path, items, warnings, event.reply_to)
        case ConfigRejected():
            return protocol.config_rejected(event.section, event.key, event.message, event.reply_to)
        case ModelsStateChanged():
            models = [
                protocol.ModelEntry(
                    id=m.id,
                    name=m.name,
                    summary=m.summary,
                    role=protocol.ModelRole(m.role),
                    recommended=m.recommended,
                    file=m.file,
                    size_bytes=m.size_bytes,
                    state=protocol.ModelState(m.state),
                    received_bytes=m.received_bytes,
                    bytes_per_second=m.bytes_per_second,
                    error=m.error,
                )
                for m in event.models
            ]
            return protocol.models_state(
                event.models_dir, models, event.reply_to, list(event.other_files)
            )
        case ToolConfirmRequested():
            return protocol.tool_confirm(
                event.turn_id, event.request_id, event.tool, event.question, event.risk
            )
        case ToolConfirmClosed():
            return protocol.tool_confirm_closed(event.request_id, event.allowed)
        case ActionRecorded():
            return protocol.action_recorded(
                event.turn_id, event.action_id, event.tool, event.summary, event.undoable
            )
        case ActionUndone():
            return protocol.action_undone(event.action_id, event.ok, event.message)
        case TimerFired():
            return protocol.timer_fired(event.timer_id, event.kind, event.label, event.missed)
        case FocusModeChanged():
            return protocol.focus_changed(event.on, event.minutes)
        case ContextCaptured():
            return protocol.context_captured(event.text, event.app, event.title)
        case ContextReplaced():
            return protocol.context_replaced(event.ok, event.message)
    return None


OUTBOUND_EVENTS: tuple[type[Event], ...] = (
    ChatStarted,
    ChatDelta,
    ChatToolChanged,
    ChatDone,
    ChatFailed,
    LlmStatusChanged,
    ConfigStateChanged,
    ConfigRejected,
    ModelsStateChanged,
    ToolConfirmRequested,
    ToolConfirmClosed,
    ActionRecorded,
    ActionUndone,
    TimerFired,
    FocusModeChanged,
    ContextCaptured,
    ContextReplaced,
)


class CoreServer:
    def __init__(
        self,
        *,
        bus: EventBus,
        token: str,
        core_version: str,
        module_statuses: Callable[[], list[ModuleStatus]],
        on_shutdown: Callable[[protocol.Reason], None],
    ) -> None:
        self._expected_auth = f"Bearer {token}".encode()
        self._core_version = core_version
        self._module_statuses = module_statuses
        self._on_shutdown = on_shutdown
        self._bus = bus
        self._server: Server | None = None
        self._active: ServerConnection | None = None
        self._outbox: asyncio.Queue[str] | None = None
        self._llm_status: LlmStatusChanged | None = None
        for event_type in OUTBOUND_EVENTS:
            bus.subscribe(event_type, self._on_outbound)

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
        outbox: asyncio.Queue[str] = asyncio.Queue()
        writer = asyncio.create_task(self._write(connection, outbox))
        logger.info("client connected")
        try:
            await self._session(connection, outbox)
        except ConnectionClosedError as exc:
            logger.info("client disconnected abnormally", extra={"fields": {"code": exc.code}})
        finally:
            self._active = None
            self._outbox = None
            writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await writer
            logger.info("client disconnected")

    async def _on_outbound(self, event: Event) -> None:
        # Runs synchronously up to put_nowait: handlers start in publish order,
        # so the outbox keeps the bus order (deltas never reorder).
        if isinstance(event, LlmStatusChanged):
            self._llm_status = event
        message = to_message(event)
        if message is not None and self._outbox is not None:
            self._outbox.put_nowait(protocol.encode(message))

    @staticmethod
    async def _write(connection: ServerConnection, outbox: asyncio.Queue[str]) -> None:
        with contextlib.suppress(ConnectionClosed):
            while True:
                await connection.send(await outbox.get())

    async def _session(self, connection: ServerConnection, outbox: asyncio.Queue[str]) -> None:
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
                    # Outbound events flow only after the handshake.
                    self._outbox = outbox
                    if self._llm_status is not None and (status := to_message(self._llm_status)):
                        outbox.put_nowait(protocol.encode(status))
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
                case protocol.ChatSendMessage():
                    effort = message.payload.effort
                    self._bus.publish(
                        ChatRequested(
                            message.id,
                            message.payload.text,
                            EffortLevel(effort.value) if effort is not None else None,
                        )
                    )
                case protocol.ChatCancelMessage():
                    self._bus.publish(ChatCancelRequested(message.payload.turn_id))
                case protocol.ChatResetMessage():
                    self._bus.publish(ChatResetRequested())
                case protocol.ConfigGetMessage():
                    self._bus.publish(ConfigGetRequested(message.id))
                case protocol.ConfigSetMessage():
                    edit = message.payload
                    self._bus.publish(
                        ConfigSetRequested(message.id, edit.section, edit.key, edit.value)
                    )
                case protocol.ConfigResetMessage():
                    reset = message.payload
                    self._bus.publish(ConfigResetRequested(message.id, reset.section, reset.key))
                case protocol.ModelsGetMessage():
                    self._bus.publish(ModelsGetRequested(message.id))
                case protocol.ModelsDownloadMessage():
                    self._bus.publish(ModelDownloadRequested(message.id, message.payload.model_id))
                case protocol.ModelsCancelMessage():
                    self._bus.publish(ModelCancelRequested(message.id, message.payload.model_id))
                case protocol.ToolAnswerMessage():
                    answer = message.payload
                    self._bus.publish(ToolAnswered(str(answer.request_id), answer.allowed))
                case protocol.ActionUndoMessage():
                    self._bus.publish(UndoRequested(message.payload.action_id))
                case protocol.ContextCaptureMessage():
                    self._bus.publish(ContextCaptureRequested())
                case protocol.ContextClearMessage():
                    self._bus.publish(ContextClearRequested())
                case protocol.ContextReplaceMessage():
                    self._bus.publish(ContextReplaceRequested(message.payload.text))
                case (
                    protocol.HelloAckMessage()
                    | protocol.PongMessage()
                    | protocol.ChatStartedMessage()
                    | protocol.ChatDeltaMessage()
                    | protocol.ChatToolMessage()
                    | protocol.ChatDoneMessage()
                    | protocol.ChatFailedMessage()
                    | protocol.LlmStatusMessage()
                    | protocol.ConfigStateMessage()
                    | protocol.ConfigRejectedMessage()
                    | protocol.ModelsStateMessage()
                    | protocol.ToolConfirmMessage()
                    | protocol.ToolConfirmClosedMessage()
                    | protocol.ActionRecordedMessage()
                    | protocol.ActionUndoneMessage()
                    | protocol.TimerFiredMessage()
                    | protocol.FocusChangedMessage()
                    | protocol.ContextCapturedMessage()
                    | protocol.ContextReplacedMessage()
                ):
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
