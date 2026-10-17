# Generated from protocol/ev-protocol.schema.json. Do not edit; run scripts/codegen-protocol.

from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, RootModel
from enum import StrEnum


class ModuleState(StrEnum):
    starting = "starting"
    ready = "ready"
    disabled = "disabled"
    failed = "failed"


class ModuleStatus(BaseModel):
    name: Annotated[str, Field(max_length=64, min_length=1)]
    state: ModuleState
    detail: Annotated[
        str | None,
        Field(
            description="User-facing explanation when state is disabled or failed.", max_length=500
        ),
    ] = None


class HelloPayload(BaseModel):
    app_version: Annotated[
        str,
        Field(description="Semantic version string of a component.", max_length=64, min_length=1),
    ]
    protocol: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]


class HelloAckPayload(BaseModel):
    core_version: Annotated[
        str,
        Field(description="Semantic version string of a component.", max_length=64, min_length=1),
    ]
    protocol: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    modules: list[ModuleStatus]


class EmptyPayload(BaseModel):
    pass


class ErrorPayload(BaseModel):
    code: Annotated[
        str,
        Field(
            description="Stable machine-readable code. New codes may be added; receivers treat unknown codes as internal.",
            pattern="^[a-z][a-z0-9_]{0,63}$",
        ),
    ]
    message: Annotated[
        str, Field(description="Short, plain, user-facing text.", max_length=300, min_length=1)
    ]
    detail: Annotated[
        str | None,
        Field(description="Technical detail for logs. Never shown in the island.", max_length=4000),
    ] = None


class Reason(StrEnum):
    app_exit = "app_exit"
    restart = "restart"


class ShutdownPayload(BaseModel):
    reason: Reason


class HelloMessage(BaseModel):
    """
    Rust -> core. First message after the WebSocket opens.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["hello"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: HelloPayload


class HelloAckMessage(BaseModel):
    """
    core -> Rust. Answer to hello.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["hello.ack"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: HelloAckPayload


class PingMessage(BaseModel):
    """
    Rust -> core. Liveness check, sent every 5 s.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["ping"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: EmptyPayload


class PongMessage(BaseModel):
    """
    core -> Rust. Answer to ping; reply_to carries the ping id.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["pong"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: EmptyPayload


class ErrorMessage(BaseModel):
    """
    Either direction. reply_to carries the id of the message that caused it, when known.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["error"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ErrorPayload


class ShutdownMessage(BaseModel):
    """
    Rust -> core. Core stops modules, closes the socket and exits with code 0.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["shutdown"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ShutdownPayload


class Effort(StrEnum):
    """
    Effort level (CLAUDE.md §5.5).
    """

    instant = "instant"
    normal = "normal"
    deep = "deep"
    max = "max"


class ChatSendPayload(BaseModel):
    text: Annotated[
        str,
        Field(
            description="User input. Core refuses text over its own limit with chat.failed.",
            max_length=100000,
        ),
    ]
    effort: Annotated[
        Effort | None, Field(description="Requested effort; omitted means the configured default.")
    ] = None


class ChatCancelPayload(BaseModel):
    turn_id: Annotated[
        str,
        Field(
            description="The id of the chat.send message that started the turn.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]


class ChatStartedPayload(BaseModel):
    turn_id: Annotated[
        str,
        Field(
            description="The id of the chat.send message that started the turn.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    effort: Effort
    model: Annotated[
        str | None,
        Field(
            description="Absent when the rule router answers without a model.",
            max_length=256,
            min_length=1,
        ),
    ] = None


class ChatDeltaPayload(BaseModel):
    turn_id: Annotated[
        str,
        Field(
            description="The id of the chat.send message that started the turn.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    text: Annotated[str, Field(description="Next piece of the reply.")]


class ChatToolState(StrEnum):
    running = "running"
    done = "done"
    failed = "failed"
    blocked = "blocked"


class ChatToolPayload(BaseModel):
    turn_id: Annotated[
        str,
        Field(
            description="The id of the chat.send message that started the turn.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    name: Annotated[str, Field(max_length=64, min_length=1)]
    state: ChatToolState


class ChatTimings(BaseModel):
    first_token_ms: Annotated[
        int | None, Field(description="Request received to first reply token.", ge=0)
    ] = None
    total_ms: Annotated[int, Field(ge=0)]
    prompt_tokens: Annotated[int | None, Field(ge=0)] = None
    generated_tokens: Annotated[int | None, Field(ge=0)] = None


class ChatDonePayload(BaseModel):
    turn_id: Annotated[
        str,
        Field(
            description="The id of the chat.send message that started the turn.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    text: Annotated[str, Field(description="The full reply.")]
    effort: Effort
    model: Annotated[
        str | None,
        Field(description="Model file name, as configured.", max_length=256, min_length=1),
    ] = None
    timings: ChatTimings
    cancelled: Annotated[
        bool, Field(description="True when a cancel or a newer message ended the turn early.")
    ]


class ChatFailedPayload(BaseModel):
    turn_id: Annotated[
        str,
        Field(
            description="The id of the chat.send message that started the turn.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    code: Annotated[str, Field(pattern="^[a-z][a-z0-9_]{0,63}$")]
    message: Annotated[
        str, Field(description="Short, plain, user-facing text.", max_length=300, min_length=1)
    ]


class LlmState(StrEnum):
    unloaded = "unloaded"
    loading = "loading"
    ready = "ready"
    failed = "failed"


class LlmStatusPayload(BaseModel):
    state: LlmState
    model: Annotated[
        str | None,
        Field(description="Model file name, as configured.", max_length=256, min_length=1),
    ] = None
    detail: Annotated[
        str | None, Field(description="User-facing explanation when failed.", max_length=300)
    ] = None


class ChatSendMessage(BaseModel):
    """
    Rust -> core. Start a turn; the message id becomes the turn id. A newer chat.send cancels a running turn.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["chat.send"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ChatSendPayload


class ChatCancelMessage(BaseModel):
    """
    Rust -> core. Stop a running turn; core still sends chat.done with cancelled = true.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["chat.cancel"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ChatCancelPayload


class ChatStartedMessage(BaseModel):
    """
    core -> Rust. A turn began.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["chat.started"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ChatStartedPayload


class ChatDeltaMessage(BaseModel):
    """
    core -> Rust. Streamed reply text.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["chat.delta"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ChatDeltaPayload


class ChatToolMessage(BaseModel):
    """
    core -> Rust. A tool step changed state.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["chat.tool"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ChatToolPayload


class ChatDoneMessage(BaseModel):
    """
    core -> Rust. A turn ended normally or was cancelled.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["chat.done"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ChatDonePayload


class ChatFailedMessage(BaseModel):
    """
    core -> Rust. A turn ended with an error.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["chat.failed"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ChatFailedPayload


class LlmStatusMessage(BaseModel):
    """
    core -> Rust. Model load state changed.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["llm.status"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: LlmStatusPayload


class SettingNav(StrEnum):
    """
    Settings section (CLAUDE.md §6.5).
    """

    general = "general"
    voice = "voice"
    models = "models"
    personality = "personality"
    appearance = "appearance"
    hotkeys = "hotkeys"
    permissions = "permissions"
    memory = "memory"
    routines = "routines"
    web = "web"
    advanced = "advanced"
    diagnostics = "diagnostics"
    about = "about"


class Kind(StrEnum):
    boolean = "boolean"
    choice = "choice"
    integer = "integer"
    text = "text"


class Option(RootModel[str]):
    root: Annotated[str, Field(max_length=64)]


class SettingItem(BaseModel):
    section: Annotated[str, Field(pattern="^[a-z][a-z0-9_]{0,63}$")]
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9_]{0,63}$")]
    nav: SettingNav
    label: Annotated[str, Field(max_length=80)]
    description: Annotated[str, Field(max_length=300)]
    kind: Kind
    default: bool | int | str
    value: bool | int | str
    options: list[Option] | None = None
    minimum: int | None = None
    maximum: int | None = None


class ConfigWarningItem(BaseModel):
    key: Annotated[str, Field(max_length=128)]
    message: Annotated[str, Field(max_length=300)]


class ConfigGetPayload(BaseModel):
    pass


class ConfigSetPayload(BaseModel):
    section: Annotated[str, Field(pattern="^[a-z][a-z0-9_]{0,63}$")]
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9_]{0,63}$")]
    value: bool | int | str


class ConfigResetPayload(BaseModel):
    section: Annotated[str, Field(pattern="^[a-z][a-z0-9_]{0,63}$")]
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9_]{0,63}$")]


class ConfigStatePayload(BaseModel):
    path: Annotated[str, Field(description="Absolute path of config.toml.", max_length=4096)]
    items: list[SettingItem]
    warnings: list[ConfigWarningItem]


class ConfigRejectedPayload(BaseModel):
    section: Annotated[str, Field(max_length=64)]
    key: Annotated[str, Field(max_length=64)]
    message: Annotated[
        str, Field(description="Short, plain, user-facing text.", max_length=300, min_length=1)
    ]


class ConfigGetMessage(BaseModel):
    """
    Rust -> core. Ask for the current settings; core answers config.state.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["config.get"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ConfigGetPayload


class ConfigSetMessage(BaseModel):
    """
    Rust -> core. Change one setting; core answers config.state or config.rejected.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["config.set"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ConfigSetPayload


class ConfigResetMessage(BaseModel):
    """
    Rust -> core. Return one setting to its default; core answers config.state.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["config.reset"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ConfigResetPayload


class ConfigStateMessage(BaseModel):
    """
    core -> Rust. Every setting with its value; also sent when config.toml changes on disk.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["config.state"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ConfigStatePayload


class ConfigRejectedMessage(BaseModel):
    """
    core -> Rust. A change was refused; config.toml is unchanged.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["config.rejected"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ConfigRejectedPayload


class ModelRole(StrEnum):
    small = "small"
    default = "default"
    large = "large"


class ModelState(StrEnum):
    available = "available"
    partial = "partial"
    downloading = "downloading"
    verifying = "verifying"
    installed = "installed"
    failed = "failed"


class ModelEntry(BaseModel):
    """
    One catalog model and its state on this PC (docs/FEATURES.md F-403).
    """

    id: Annotated[
        str,
        Field(
            description="Catalog model id (core/ev_core/models/manifest.json).",
            pattern="^[a-z0-9][a-z0-9.\\-]{1,63}$",
        ),
    ]
    name: Annotated[str, Field(max_length=40)]
    summary: Annotated[str, Field(max_length=80)]
    role: ModelRole
    recommended: bool
    file: Annotated[
        str, Field(description="Model file name, as configured.", max_length=256, min_length=1)
    ]
    size_bytes: Annotated[int, Field(ge=0)]
    state: ModelState
    received_bytes: Annotated[int, Field(ge=0)]
    bytes_per_second: Annotated[int, Field(ge=0)]
    error: Annotated[
        str | None, Field(description="User-facing reason when state is failed.", max_length=300)
    ] = None


class ModelsGetPayload(BaseModel):
    pass


class ModelRequestPayload(BaseModel):
    model_id: Annotated[
        str,
        Field(
            description="Catalog model id (core/ev_core/models/manifest.json).",
            pattern="^[a-z0-9][a-z0-9.\\-]{1,63}$",
        ),
    ]


class ModelsStatePayload(BaseModel):
    models_dir: Annotated[
        str, Field(description="Absolute path of the models folder.", max_length=4096)
    ]
    models: list[ModelEntry]


class ModelsGetMessage(BaseModel):
    """
    Rust -> core. Ask for the model list; core answers models.state.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["models.get"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ModelsGetPayload


class ModelsDownloadMessage(BaseModel):
    """
    Rust -> core. Download a catalog model (resumes a partial download). Core answers models.state.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["models.download"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ModelRequestPayload


class ModelsCancelMessage(BaseModel):
    """
    Rust -> core. Stop a download; the partial file is kept for a later resume.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["models.cancel"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ModelRequestPayload


class ModelsStateMessage(BaseModel):
    """
    core -> Rust. Every catalog model with its state; also sent on download progress (at most 4/s).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    v: Annotated[
        int,
        Field(
            description="Protocol version of the sender. Receivers compare it with their own and reply with an error of code protocol_mismatch when they differ.",
            ge=1,
        ),
    ]
    type: Literal["models.state"]
    id: Annotated[
        str,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ]
    reply_to: Annotated[
        str | None,
        Field(
            description="UUID v4, unique per message.",
            pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        ),
    ] = None
    payload: ModelsStatePayload


class EvMessage(
    RootModel[
        HelloMessage
        | HelloAckMessage
        | PingMessage
        | PongMessage
        | ErrorMessage
        | ShutdownMessage
        | ChatSendMessage
        | ChatCancelMessage
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
    ]
):
    root: Annotated[
        HelloMessage
        | HelloAckMessage
        | PingMessage
        | PongMessage
        | ErrorMessage
        | ShutdownMessage
        | ChatSendMessage
        | ChatCancelMessage
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
        | ModelsStateMessage,
        Field(
            description="EV wire protocol between the Tauri app (Rust) and ev-core (Python). One JSON object per WebSocket text frame. Changes are additive; removing or renaming a field requires a protocol version bump.",
            title="EvMessage",
        ),
    ]
