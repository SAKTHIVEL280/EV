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


class EvMessage(
    RootModel[
        HelloMessage | HelloAckMessage | PingMessage | PongMessage | ErrorMessage | ShutdownMessage
    ]
):
    root: Annotated[
        HelloMessage | HelloAckMessage | PingMessage | PongMessage | ErrorMessage | ShutdownMessage,
        Field(
            description="EV wire protocol between the Tauri app (Rust) and ev-core (Python). One JSON object per WebSocket text frame. Changes are additive; removing or renaming a field requires a protocol version bump.",
            title="EvMessage",
        ),
    ]
