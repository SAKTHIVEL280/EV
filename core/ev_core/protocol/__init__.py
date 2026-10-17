"""EV wire protocol (docs/ARCHITECTURE.md §3).

Types come from ``generated.py`` (from protocol/ev-protocol.schema.json); this
module adds the discriminated union, encode/decode and message constructors.
"""

import json
import re
import uuid
from typing import Annotated, Final

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from ev_core.errors import EvError
from ev_core.protocol.generated import (
    ActionRecordedMessage,
    ActionRecordedPayload,
    ActionUndoMessage,
    ActionUndoneMessage,
    ActionUndonePayload,
    ChatCancelMessage,
    ChatCancelPayload,
    ChatDeltaMessage,
    ChatDeltaPayload,
    ChatDoneMessage,
    ChatDonePayload,
    ChatFailedMessage,
    ChatFailedPayload,
    ChatResetMessage,
    ChatSendMessage,
    ChatSendPayload,
    ChatStartedMessage,
    ChatStartedPayload,
    ChatTimings,
    ChatToolMessage,
    ChatToolPayload,
    ChatToolState,
    ConfigGetMessage,
    ConfigGetPayload,
    ConfigRejectedMessage,
    ConfigRejectedPayload,
    ConfigResetMessage,
    ConfigResetPayload,
    ConfigSetMessage,
    ConfigSetPayload,
    ConfigStateMessage,
    ConfigStatePayload,
    ConfigWarningItem,
    Effort,
    EmptyPayload,
    ErrorMessage,
    ErrorPayload,
    FocusChangedMessage,
    FocusChangedPayload,
    HelloAckMessage,
    HelloAckPayload,
    HelloMessage,
    HelloPayload,
    LlmState,
    LlmStatusMessage,
    LlmStatusPayload,
    ModelEntry,
    ModelRequestPayload,
    ModelRole,
    ModelsCancelMessage,
    ModelsDownloadMessage,
    ModelsGetMessage,
    ModelsGetPayload,
    ModelsStateMessage,
    ModelsStatePayload,
    ModelState,
    ModuleState,
    ModuleStatus,
    PingMessage,
    PongMessage,
    Reason,
    SettingItem,
    SettingNav,
    ShutdownMessage,
    ShutdownPayload,
    TimerFiredMessage,
    TimerFiredPayload,
    ToolAnswerMessage,
    ToolConfirmClosedMessage,
    ToolConfirmClosedPayload,
    ToolConfirmMessage,
    ToolConfirmPayload,
)
from ev_core.protocol.generated import (
    Kind as SettingKind,
)
from ev_core.protocol.generated import (
    Kind1 as TimerKind,
)
from ev_core.protocol.generated import (
    Risk as ToolRisk,
)
from ev_core.protocol.generated import (
    Role as SettingRole,
)
from ev_core.protocol.generated import (
    Widget as SettingWidget,
)

PROTOCOL_VERSION: Final = 1
"""Must equal ``x-ev-protocol-version`` in the schema (enforced by a test)."""

type AnyMessage = Annotated[
    HelloMessage
    | HelloAckMessage
    | PingMessage
    | PongMessage
    | ErrorMessage
    | ShutdownMessage
    | ChatSendMessage
    | ChatCancelMessage
    | ChatResetMessage
    | ChatStartedMessage
    | ChatDeltaMessage
    | ChatToolMessage
    | ChatDoneMessage
    | ChatFailedMessage
    | LlmStatusMessage
    | ConfigGetMessage
    | ConfigSetMessage
    | ConfigResetMessage
    | ConfigStateMessage
    | ConfigRejectedMessage
    | ModelsGetMessage
    | ModelsDownloadMessage
    | ModelsCancelMessage
    | ModelsStateMessage
    | ToolConfirmMessage
    | ToolAnswerMessage
    | ToolConfirmClosedMessage
    | ActionRecordedMessage
    | ActionUndoMessage
    | ActionUndoneMessage
    | TimerFiredMessage
    | FocusChangedMessage,
    Field(discriminator="type"),
]

_ADAPTER: Final[TypeAdapter[AnyMessage]] = TypeAdapter(AnyMessage)
_UUID_V4: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class DecodeError(EvError):
    """A frame is not a valid protocol message. ``reply_to`` is its id when readable."""

    def __init__(self, detail: str, reply_to: str | None) -> None:
        super().__init__("EV received a message it doesn't understand.", detail)
        self.reply_to = reply_to


def decode(raw: str | bytes) -> AnyMessage:
    try:
        return _ADAPTER.validate_json(raw, strict=True)
    except ValidationError as exc:
        raise DecodeError(str(exc), _readable_id(raw)) from exc


def encode(message: BaseModel) -> str:
    return message.model_dump_json(exclude_none=True)


def new_id() -> str:
    return str(uuid.uuid4())


def hello(app_version: str) -> HelloMessage:
    return HelloMessage(
        v=PROTOCOL_VERSION,
        type="hello",
        id=new_id(),
        payload=HelloPayload(app_version=app_version, protocol=PROTOCOL_VERSION),
    )


def hello_ack(reply_to: str, core_version: str, modules: list[ModuleStatus]) -> HelloAckMessage:
    return HelloAckMessage(
        v=PROTOCOL_VERSION,
        type="hello.ack",
        id=new_id(),
        reply_to=reply_to,
        payload=HelloAckPayload(
            core_version=core_version, protocol=PROTOCOL_VERSION, modules=modules
        ),
    )


def ping() -> PingMessage:
    return PingMessage(v=PROTOCOL_VERSION, type="ping", id=new_id(), payload=EmptyPayload())


def pong(reply_to: str) -> PongMessage:
    return PongMessage(
        v=PROTOCOL_VERSION, type="pong", id=new_id(), reply_to=reply_to, payload=EmptyPayload()
    )


def error(
    code: str, message: str, detail: str | None = None, reply_to: str | None = None
) -> ErrorMessage:
    return ErrorMessage(
        v=PROTOCOL_VERSION,
        type="error",
        id=new_id(),
        reply_to=reply_to,
        payload=ErrorPayload(code=code, message=message, detail=detail),
    )


def shutdown(reason: Reason) -> ShutdownMessage:
    return ShutdownMessage(
        v=PROTOCOL_VERSION, type="shutdown", id=new_id(), payload=ShutdownPayload(reason=reason)
    )


def chat_send(text: str, effort: Effort | None = None) -> ChatSendMessage:
    return ChatSendMessage(
        v=PROTOCOL_VERSION,
        type="chat.send",
        id=new_id(),
        payload=ChatSendPayload(text=text, effort=effort),
    )


def chat_cancel(turn_id: str) -> ChatCancelMessage:
    return ChatCancelMessage(
        v=PROTOCOL_VERSION,
        type="chat.cancel",
        id=new_id(),
        payload=ChatCancelPayload(turn_id=turn_id),
    )


def chat_reset() -> ChatResetMessage:
    return ChatResetMessage(
        v=PROTOCOL_VERSION, type="chat.reset", id=new_id(), payload=EmptyPayload()
    )


def chat_started(turn_id: str, effort: Effort, model: str | None) -> ChatStartedMessage:
    return ChatStartedMessage(
        v=PROTOCOL_VERSION,
        type="chat.started",
        id=new_id(),
        reply_to=turn_id,
        payload=ChatStartedPayload(turn_id=turn_id, effort=effort, model=model),
    )


def chat_delta(turn_id: str, text: str) -> ChatDeltaMessage:
    return ChatDeltaMessage(
        v=PROTOCOL_VERSION,
        type="chat.delta",
        id=new_id(),
        payload=ChatDeltaPayload(turn_id=turn_id, text=text),
    )


def chat_tool(turn_id: str, name: str, state: ChatToolState) -> ChatToolMessage:
    return ChatToolMessage(
        v=PROTOCOL_VERSION,
        type="chat.tool",
        id=new_id(),
        payload=ChatToolPayload(turn_id=turn_id, name=name, state=state),
    )


def chat_done(
    turn_id: str,
    text: str,
    effort: Effort,
    model: str | None,
    timings: ChatTimings,
    *,
    cancelled: bool,
) -> ChatDoneMessage:
    return ChatDoneMessage(
        v=PROTOCOL_VERSION,
        type="chat.done",
        id=new_id(),
        reply_to=turn_id,
        payload=ChatDonePayload(
            turn_id=turn_id,
            text=text,
            effort=effort,
            model=model,
            timings=timings,
            cancelled=cancelled,
        ),
    )


def chat_failed(turn_id: str, code: str, message: str) -> ChatFailedMessage:
    return ChatFailedMessage(
        v=PROTOCOL_VERSION,
        type="chat.failed",
        id=new_id(),
        reply_to=turn_id,
        payload=ChatFailedPayload(turn_id=turn_id, code=code, message=message),
    )


def llm_status(state: LlmState, model: str | None, detail: str | None = None) -> LlmStatusMessage:
    return LlmStatusMessage(
        v=PROTOCOL_VERSION,
        type="llm.status",
        id=new_id(),
        payload=LlmStatusPayload(state=state, model=model, detail=detail),
    )


def config_get() -> ConfigGetMessage:
    return ConfigGetMessage(
        v=PROTOCOL_VERSION, type="config.get", id=new_id(), payload=ConfigGetPayload()
    )


def config_set(section: str, key: str, value: bool | int | str) -> ConfigSetMessage:
    return ConfigSetMessage(
        v=PROTOCOL_VERSION,
        type="config.set",
        id=new_id(),
        payload=ConfigSetPayload(section=section, key=key, value=value),
    )


def config_reset(section: str, key: str) -> ConfigResetMessage:
    return ConfigResetMessage(
        v=PROTOCOL_VERSION,
        type="config.reset",
        id=new_id(),
        payload=ConfigResetPayload(section=section, key=key),
    )


def config_state(
    path: str,
    items: list[SettingItem],
    warnings: list[ConfigWarningItem],
    reply_to: str | None = None,
) -> ConfigStateMessage:
    return ConfigStateMessage(
        v=PROTOCOL_VERSION,
        type="config.state",
        id=new_id(),
        reply_to=reply_to,
        payload=ConfigStatePayload(path=path, items=items, warnings=warnings),
    )


def config_rejected(
    section: str, key: str, message: str, reply_to: str | None = None
) -> ConfigRejectedMessage:
    return ConfigRejectedMessage(
        v=PROTOCOL_VERSION,
        type="config.rejected",
        id=new_id(),
        reply_to=reply_to,
        payload=ConfigRejectedPayload(section=section, key=key, message=message),
    )


def models_get() -> ModelsGetMessage:
    return ModelsGetMessage(
        v=PROTOCOL_VERSION, type="models.get", id=new_id(), payload=ModelsGetPayload()
    )


def models_download(model_id: str) -> ModelsDownloadMessage:
    return ModelsDownloadMessage(
        v=PROTOCOL_VERSION,
        type="models.download",
        id=new_id(),
        payload=ModelRequestPayload(model_id=model_id),
    )


def models_cancel(model_id: str) -> ModelsCancelMessage:
    return ModelsCancelMessage(
        v=PROTOCOL_VERSION,
        type="models.cancel",
        id=new_id(),
        payload=ModelRequestPayload(model_id=model_id),
    )


def models_state(
    models_dir: str,
    models: list[ModelEntry],
    reply_to: str | None = None,
    other_files: list[str] | None = None,
) -> ModelsStateMessage:
    return ModelsStateMessage(
        v=PROTOCOL_VERSION,
        type="models.state",
        id=new_id(),
        reply_to=reply_to,
        payload=ModelsStatePayload(
            models_dir=models_dir, models=models, other_files=other_files or None
        ),
    )


def tool_confirm(
    turn_id: str, request_id: str, tool: str, question: str, risk: str
) -> ToolConfirmMessage:
    return ToolConfirmMessage(
        v=PROTOCOL_VERSION,
        type="tool.confirm",
        id=new_id(),
        payload=ToolConfirmPayload(
            turn_id=turn_id,
            request_id=request_id,
            tool=tool,
            question=question,
            risk=ToolRisk(risk),
        ),
    )


def tool_confirm_closed(request_id: str, allowed: bool) -> ToolConfirmClosedMessage:
    return ToolConfirmClosedMessage(
        v=PROTOCOL_VERSION,
        type="tool.confirm_closed",
        id=new_id(),
        payload=ToolConfirmClosedPayload(request_id=request_id, allowed=allowed),
    )


def action_recorded(
    turn_id: str, action_id: int, tool: str, summary: str, undoable: bool
) -> ActionRecordedMessage:
    return ActionRecordedMessage(
        v=PROTOCOL_VERSION,
        type="action.recorded",
        id=new_id(),
        payload=ActionRecordedPayload(
            turn_id=turn_id, action_id=action_id, tool=tool, summary=summary, undoable=undoable
        ),
    )


def action_undone(action_id: int, ok: bool, message: str) -> ActionUndoneMessage:
    return ActionUndoneMessage(
        v=PROTOCOL_VERSION,
        type="action.undone",
        id=new_id(),
        payload=ActionUndonePayload(action_id=action_id, ok=ok, message=message),
    )


def timer_fired(timer_id: int, kind: str, label: str, missed: bool) -> TimerFiredMessage:
    return TimerFiredMessage(
        v=PROTOCOL_VERSION,
        type="timer.fired",
        id=new_id(),
        payload=TimerFiredPayload(
            timer_id=timer_id, kind=TimerKind(kind), label=label, missed=missed
        ),
    )


def focus_changed(on: bool, minutes: int | None) -> FocusChangedMessage:
    return FocusChangedMessage(
        v=PROTOCOL_VERSION,
        type="focus.changed",
        id=new_id(),
        payload=FocusChangedPayload(on=on, minutes=minutes),
    )


def _readable_id(raw: str | bytes) -> str | None:
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(obj, dict):
        candidate = obj.get("id")
        if isinstance(candidate, str) and _UUID_V4.match(candidate):
            return candidate
    return None


__all__ = [
    "PROTOCOL_VERSION",
    "ActionRecordedMessage",
    "ActionUndoMessage",
    "ActionUndoneMessage",
    "AnyMessage",
    "ChatCancelMessage",
    "ChatDeltaMessage",
    "ChatDoneMessage",
    "ChatFailedMessage",
    "ChatResetMessage",
    "ChatSendMessage",
    "ChatStartedMessage",
    "ChatTimings",
    "ChatToolMessage",
    "ChatToolState",
    "ConfigGetMessage",
    "ConfigRejectedMessage",
    "ConfigResetMessage",
    "ConfigSetMessage",
    "ConfigStateMessage",
    "ConfigWarningItem",
    "DecodeError",
    "Effort",
    "ErrorMessage",
    "FocusChangedMessage",
    "HelloAckMessage",
    "HelloMessage",
    "LlmState",
    "LlmStatusMessage",
    "ModelEntry",
    "ModelRole",
    "ModelState",
    "ModelsCancelMessage",
    "ModelsDownloadMessage",
    "ModelsGetMessage",
    "ModelsStateMessage",
    "ModuleState",
    "ModuleStatus",
    "PingMessage",
    "PongMessage",
    "Reason",
    "SettingItem",
    "SettingKind",
    "SettingNav",
    "SettingRole",
    "SettingWidget",
    "ShutdownMessage",
    "TimerFiredMessage",
    "ToolAnswerMessage",
    "ToolConfirmClosedMessage",
    "ToolConfirmMessage",
    "action_recorded",
    "action_undone",
    "chat_cancel",
    "chat_delta",
    "chat_done",
    "chat_failed",
    "chat_reset",
    "chat_send",
    "chat_started",
    "chat_tool",
    "config_get",
    "config_rejected",
    "config_reset",
    "config_set",
    "config_state",
    "decode",
    "encode",
    "error",
    "focus_changed",
    "hello",
    "hello_ack",
    "llm_status",
    "models_cancel",
    "models_download",
    "models_get",
    "models_state",
    "new_id",
    "ping",
    "pong",
    "shutdown",
    "timer_fired",
    "tool_confirm",
    "tool_confirm_closed",
]
