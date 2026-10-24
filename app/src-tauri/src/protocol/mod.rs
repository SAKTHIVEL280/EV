//! EV wire protocol (docs/ARCHITECTURE.md §3).
//!
//! Types are generated from `protocol/ev-protocol.schema.json` at build time.
//! The generated `EvMessage` union is untagged and does not check `type`
//! (typify ignores `const`), so a `pong` would parse as a `ping`. Decoding
//! therefore dispatches on `type` first and deserializes into the matching
//! struct; [`Message`] is the only message type the rest of the app uses.

#[allow(
    clippy::all,
    clippy::pedantic,
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    missing_debug_implementations,
    dead_code
)]
pub mod generated {
    include!(concat!(env!("OUT_DIR"), "/protocol.rs"));
}

use std::num::NonZeroU64;

use generated::{
    ChatCancelPayload, ChatSendPayload, ConfigGetPayload, ConfigResetPayload, ConfigSetPayload,
    Effort, EmptyPayload, HelloPayload, ModelId, ModelRequestPayload, ModelsGetPayload,
    ProtocolVersion, SettingName, SettingValue, ShutdownPayload, ShutdownPayloadReason,
};
use serde_json::Value;
use thiserror::Error;

use crate::error::AppError;
use crate::secrets::uuid_v4;

/// Must equal `x-ev-protocol-version` in the schema (enforced by a test).
pub const PROTOCOL_VERSION: u64 = 1;

/// One table drives the enum, decoding, encoding and version access, so a
/// message type cannot be added to one and forgotten in another.
macro_rules! messages {
    ($($variant:ident($ty:ident) = $wire:literal,)+) => {
        #[derive(Clone, Debug)]
        pub enum Message {
            $($variant(generated::$ty),)+
        }

        impl Message {
            /// Protocol version declared by the sender in the envelope.
            #[must_use]
            pub fn version(&self) -> u64 {
                match self {
                    $(Self::$variant(m) => m.v.0.get(),)+
                }
            }

            /// The wire `type` of this message.
            #[must_use]
            pub fn kind(&self) -> &'static str {
                match self {
                    $(Self::$variant(_) => $wire,)+
                }
            }
        }

        /// Parse one WebSocket text frame.
        ///
        /// # Errors
        /// When the frame is not a valid protocol message.
        pub fn decode(text: &str) -> Result<Message, DecodeError> {
            let value: Value = serde_json::from_str(text)?;
            let kind = value
                .get("type")
                .and_then(Value::as_str)
                .ok_or(DecodeError::MissingType)?
                .to_owned();
            match kind.as_str() {
                $($wire => serde_json::from_value(value)
                    .map(Message::$variant)
                    .map_err(|source| DecodeError::Invalid { kind: $wire, source }),)+
                _ => Err(DecodeError::UnknownType(kind)),
            }
        }

        /// Serialize one message to a WebSocket text frame.
        ///
        /// # Errors
        /// Never in practice: every generated type serializes to JSON.
        pub fn encode(message: &Message) -> Result<String, serde_json::Error> {
            match message {
                $(Message::$variant(m) => serde_json::to_string(m),)+
            }
        }
    };
}

messages! {
    Hello(HelloMessage) = "hello",
    HelloAck(HelloAckMessage) = "hello.ack",
    Ping(PingMessage) = "ping",
    Pong(PongMessage) = "pong",
    Error(ErrorMessage) = "error",
    Shutdown(ShutdownMessage) = "shutdown",
    ChatSend(ChatSendMessage) = "chat.send",
    ChatCancel(ChatCancelMessage) = "chat.cancel",
    ChatReset(ChatResetMessage) = "chat.reset",
    ChatStarted(ChatStartedMessage) = "chat.started",
    ChatDelta(ChatDeltaMessage) = "chat.delta",
    ChatTool(ChatToolMessage) = "chat.tool",
    ChatDone(ChatDoneMessage) = "chat.done",
    ChatFailed(ChatFailedMessage) = "chat.failed",
    LlmStatus(LlmStatusMessage) = "llm.status",
    ConfigGet(ConfigGetMessage) = "config.get",
    ConfigSet(ConfigSetMessage) = "config.set",
    ConfigReset(ConfigResetMessage) = "config.reset",
    ConfigState(ConfigStateMessage) = "config.state",
    ConfigRejected(ConfigRejectedMessage) = "config.rejected",
    ModelsGet(ModelsGetMessage) = "models.get",
    ModelsDownload(ModelsDownloadMessage) = "models.download",
    ModelsCancel(ModelsCancelMessage) = "models.cancel",
    ModelsState(ModelsStateMessage) = "models.state",
    ToolConfirm(ToolConfirmMessage) = "tool.confirm",
    ToolAnswer(ToolAnswerMessage) = "tool.answer",
    ToolConfirmClosed(ToolConfirmClosedMessage) = "tool.confirm_closed",
    ActionRecorded(ActionRecordedMessage) = "action.recorded",
    ActionUndo(ActionUndoMessage) = "action.undo",
    ActionUndone(ActionUndoneMessage) = "action.undone",
    TimerFired(TimerFiredMessage) = "timer.fired",
    FocusChanged(FocusChangedMessage) = "focus.changed",
    ContextCapture(ContextCaptureMessage) = "context.capture",
    ContextCaptured(ContextCapturedMessage) = "context.captured",
    ContextClear(ContextClearMessage) = "context.clear",
    ContextReplace(ContextReplaceMessage) = "context.replace",
    ContextReplaced(ContextReplacedMessage) = "context.replaced",
}

/// Who sends a message type.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Direction {
    /// Core to app: forwarded to the app's observers.
    FromCore,
    /// App to core.
    ToCore,
    /// Handshake and session control, handled by the session itself.
    Session,
}

impl Message {
    /// Exhaustive on purpose: a new message type does not compile until it says
    /// which way it goes (found in beta 2: new core messages were dropped as
    /// "unexpected" because the session's list missed them).
    #[must_use]
    pub fn direction(&self) -> Direction {
        match self {
            Self::Hello(_)
            | Self::HelloAck(_)
            | Self::Ping(_)
            | Self::Pong(_)
            | Self::Error(_)
            | Self::Shutdown(_) => Direction::Session,
            Self::ChatSend(_)
            | Self::ChatCancel(_)
            | Self::ChatReset(_)
            | Self::ConfigGet(_)
            | Self::ConfigSet(_)
            | Self::ConfigReset(_)
            | Self::ModelsGet(_)
            | Self::ModelsDownload(_)
            | Self::ModelsCancel(_)
            | Self::ToolAnswer(_)
            | Self::ActionUndo(_)
            | Self::ContextCapture(_)
            | Self::ContextClear(_)
            | Self::ContextReplace(_) => Direction::ToCore,
            Self::ChatStarted(_)
            | Self::ChatDelta(_)
            | Self::ChatTool(_)
            | Self::ChatDone(_)
            | Self::ChatFailed(_)
            | Self::LlmStatus(_)
            | Self::ConfigState(_)
            | Self::ConfigRejected(_)
            | Self::ModelsState(_)
            | Self::ToolConfirm(_)
            | Self::ToolConfirmClosed(_)
            | Self::ActionRecorded(_)
            | Self::ActionUndone(_)
            | Self::TimerFired(_)
            | Self::FocusChanged(_)
            | Self::ContextCaptured(_)
            | Self::ContextReplaced(_) => Direction::FromCore,
        }
    }
}

#[derive(Debug, Error)]
pub enum DecodeError {
    #[error("not JSON: {0}")]
    Json(#[from] serde_json::Error),
    #[error("missing or non-string \"type\"")]
    MissingType,
    #[error("unknown message type {0:?}")]
    UnknownType(String),
    #[error("invalid {kind} message: {source}")]
    Invalid {
        kind: &'static str,
        source: serde_json::Error,
    },
}

fn version() -> ProtocolVersion {
    // PROTOCOL_VERSION is a non-zero constant.
    ProtocolVersion(NonZeroU64::new(PROTOCOL_VERSION).unwrap_or(NonZeroU64::MIN))
}

fn id() -> Result<generated::MessageId, AppError> {
    uuid_v4()?
        .parse()
        .map_err(|e: generated::error::ConversionError| AppError::Random(e.to_string()))
}

/// # Errors
/// When the OS random source fails or `app_version` is not a valid version string.
pub fn hello(app_version: &str) -> Result<Message, AppError> {
    let app_version = app_version
        .parse()
        .map_err(|e: generated::error::ConversionError| {
            AppError::ProtocolMismatch(e.to_string())
        })?;
    Ok(Message::Hello(generated::HelloMessage {
        id: id()?,
        payload: HelloPayload {
            app_version,
            protocol: version(),
        },
        reply_to: None,
        type_: "hello".into(),
        v: version(),
    }))
}

/// # Errors
/// When the OS random source fails.
pub fn ping() -> Result<Message, AppError> {
    Ok(Message::Ping(generated::PingMessage {
        id: id()?,
        payload: EmptyPayload(serde_json::Map::new()),
        reply_to: None,
        type_: "ping".into(),
        v: version(),
    }))
}

/// # Errors
/// When the OS random source fails.
pub fn shutdown(reason: ShutdownPayloadReason) -> Result<Message, AppError> {
    Ok(Message::Shutdown(generated::ShutdownMessage {
        id: id()?,
        payload: ShutdownPayload { reason },
        reply_to: None,
        type_: "shutdown".into(),
        v: version(),
    }))
}

/// # Errors
/// When the OS random source fails or the text exceeds the schema limit.
pub fn chat_send(text: &str, effort: Option<Effort>) -> Result<Message, AppError> {
    let text = text
        .parse()
        .map_err(|e: generated::error::ConversionError| {
            AppError::ProtocolMismatch(e.to_string())
        })?;
    Ok(Message::ChatSend(generated::ChatSendMessage {
        id: id()?,
        payload: ChatSendPayload { effort, text },
        reply_to: None,
        type_: "chat.send".into(),
        v: version(),
    }))
}

/// # Errors
/// When the OS random source fails or `turn_id` is not a message id.
pub fn chat_cancel(turn_id: &str) -> Result<Message, AppError> {
    let turn_id = turn_id
        .parse()
        .map_err(|e: generated::error::ConversionError| {
            AppError::ProtocolMismatch(e.to_string())
        })?;
    Ok(Message::ChatCancel(generated::ChatCancelMessage {
        id: id()?,
        payload: ChatCancelPayload {
            turn_id: generated::TurnId(turn_id),
        },
        reply_to: None,
        type_: "chat.cancel".into(),
        v: version(),
    }))
}

/// New chat (F-414): core cancels any running turn and clears its history.
///
/// # Errors
/// When the OS random source fails.
pub fn chat_reset() -> Result<Message, AppError> {
    Ok(Message::ChatReset(generated::ChatResetMessage {
        id: id()?,
        payload: EmptyPayload(serde_json::Map::new()),
        reply_to: None,
        type_: "chat.reset".into(),
        v: version(),
    }))
}

/// The user's answer to `tool.confirm` (F-418).
///
/// # Errors
/// When the OS random source fails or `request_id` is not a message id.
pub fn tool_answer(request_id: &str, allowed: bool) -> Result<Message, AppError> {
    let request_id: generated::MessageId =
        request_id
            .parse()
            .map_err(|e: generated::error::ConversionError| {
                AppError::ProtocolMismatch(e.to_string())
            })?;
    Ok(Message::ToolAnswer(generated::ToolAnswerMessage {
        id: id()?,
        payload: generated::ToolAnswerPayload {
            allowed,
            request_id,
        },
        reply_to: None,
        type_: "tool.answer".into(),
        v: version(),
    }))
}

/// Undo one action, or the latest when `action_id` is `None` (F-111).
///
/// # Errors
/// When the OS random source fails.
pub fn action_undo(action_id: Option<u32>) -> Result<Message, AppError> {
    Ok(Message::ActionUndo(generated::ActionUndoMessage {
        id: id()?,
        payload: generated::ActionUndoPayload {
            action_id: action_id.and_then(|n| NonZeroU64::new(u64::from(n))),
        },
        reply_to: None,
        type_: "action.undo".into(),
        v: version(),
    }))
}

/// Read the selection in the app the user was in (F-201).
///
/// # Errors
/// When the OS random source fails.
pub fn context_capture() -> Result<Message, AppError> {
    Ok(Message::ContextCapture(generated::ContextCaptureMessage {
        id: id()?,
        payload: EmptyPayload(serde_json::Map::new()),
        reply_to: None,
        type_: "context.capture".into(),
        v: version(),
    }))
}

/// The user removed the selection chip.
///
/// # Errors
/// When the OS random source fails.
pub fn context_clear() -> Result<Message, AppError> {
    Ok(Message::ContextClear(generated::ContextClearMessage {
        id: id()?,
        payload: EmptyPayload(serde_json::Map::new()),
        reply_to: None,
        type_: "context.clear".into(),
        v: version(),
    }))
}

/// Replace the captured selection (F-202).
///
/// # Errors
/// When the OS random source fails or the text is too long for the protocol.
pub fn context_replace(text: &str) -> Result<Message, AppError> {
    let text = text
        .parse()
        .map_err(|e: generated::error::ConversionError| {
            AppError::ProtocolMismatch(e.to_string())
        })?;
    Ok(Message::ContextReplace(generated::ContextReplaceMessage {
        id: id()?,
        payload: generated::ContextReplacePayload { text },
        reply_to: None,
        type_: "context.replace".into(),
        v: version(),
    }))
}

fn setting_name(name: &str) -> Result<SettingName, AppError> {
    name.parse()
        .map_err(|e: generated::error::ConversionError| AppError::ProtocolMismatch(e.to_string()))
}

/// # Errors
/// When the OS random source fails.
pub fn config_get() -> Result<Message, AppError> {
    Ok(Message::ConfigGet(generated::ConfigGetMessage {
        id: id()?,
        payload: ConfigGetPayload(serde_json::Map::new()),
        reply_to: None,
        type_: "config.get".into(),
        v: version(),
    }))
}

/// # Errors
/// When the OS random source fails or a name is not a setting name.
pub fn config_set(section: &str, key: &str, value: SettingValue) -> Result<Message, AppError> {
    Ok(Message::ConfigSet(generated::ConfigSetMessage {
        id: id()?,
        payload: ConfigSetPayload {
            key: setting_name(key)?,
            section: setting_name(section)?,
            value,
        },
        reply_to: None,
        type_: "config.set".into(),
        v: version(),
    }))
}

/// # Errors
/// When the OS random source fails or a name is not a setting name.
pub fn config_reset(section: &str, key: &str) -> Result<Message, AppError> {
    Ok(Message::ConfigReset(generated::ConfigResetMessage {
        id: id()?,
        payload: ConfigResetPayload {
            key: setting_name(key)?,
            section: setting_name(section)?,
        },
        reply_to: None,
        type_: "config.reset".into(),
        v: version(),
    }))
}

/// # Errors
/// When the OS random source fails.
pub fn models_get() -> Result<Message, AppError> {
    Ok(Message::ModelsGet(generated::ModelsGetMessage {
        id: id()?,
        payload: ModelsGetPayload(serde_json::Map::new()),
        reply_to: None,
        type_: "models.get".into(),
        v: version(),
    }))
}

fn model_id(id: &str) -> Result<ModelId, AppError> {
    id.parse()
        .map_err(|e: generated::error::ConversionError| AppError::ProtocolMismatch(e.to_string()))
}

/// # Errors
/// When the OS random source fails or `model` is not a model id.
pub fn models_download(model: &str) -> Result<Message, AppError> {
    Ok(Message::ModelsDownload(generated::ModelsDownloadMessage {
        id: id()?,
        payload: ModelRequestPayload {
            model_id: model_id(model)?,
        },
        reply_to: None,
        type_: "models.download".into(),
        v: version(),
    }))
}

/// # Errors
/// When the OS random source fails or `model` is not a model id.
pub fn models_cancel(model: &str) -> Result<Message, AppError> {
    Ok(Message::ModelsCancel(generated::ModelsCancelMessage {
        id: id()?,
        payload: ModelRequestPayload {
            model_id: model_id(model)?,
        },
        reply_to: None,
        type_: "models.cancel".into(),
        v: version(),
    }))
}

#[cfg(test)]
mod tests {

    #[test]
    fn every_fixture_has_a_direction_matching_its_description() {
        let schema: serde_json::Value =
            serde_json::from_str(include_str!("../../../../protocol/ev-protocol.schema.json"))
                .unwrap();
        let dir =
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../protocol/fixtures/valid");
        for entry in std::fs::read_dir(dir).unwrap() {
            let raw = std::fs::read_to_string(entry.unwrap().path()).unwrap();
            let Ok(message) = decode(&raw) else { continue };
            if message.direction() == Direction::Session {
                continue;
            }
            let kind = message.kind();
            // Each message definition's description starts with its direction.
            let description = schema["$defs"]
                .as_object()
                .unwrap()
                .values()
                .find(|d| d["properties"]["type"]["const"] == kind)
                .and_then(|d| d["description"].as_str())
                .unwrap_or_default()
                .to_lowercase();
            let expected = if description.starts_with("core ->") {
                Direction::FromCore
            } else if description.starts_with("rust ->") {
                Direction::ToCore
            } else {
                continue;
            };
            assert_eq!(message.direction(), expected, "{kind}");
        }
    }

    use std::fs;
    use std::path::{Path, PathBuf};

    use super::*;

    fn protocol_dir() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../protocol")
    }

    fn fixtures(kind: &str) -> Vec<(String, String)> {
        let mut out: Vec<(String, String)> =
            fs::read_dir(protocol_dir().join("fixtures").join(kind))
                .unwrap()
                .map(|e| e.unwrap().path())
                .filter(|p| p.extension().is_some_and(|x| x == "json"))
                .map(|p| {
                    (
                        p.file_name().unwrap().to_string_lossy().into_owned(),
                        fs::read_to_string(&p).unwrap(),
                    )
                })
                .collect();
        out.sort();
        assert!(!out.is_empty(), "no {kind} fixtures");
        out
    }

    #[test]
    fn protocol_version_matches_schema() {
        let schema: Value = serde_json::from_str(
            &fs::read_to_string(protocol_dir().join("ev-protocol.schema.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(
            schema["x-ev-protocol-version"].as_u64(),
            Some(PROTOCOL_VERSION)
        );
    }

    #[test]
    fn valid_fixtures_decode_and_round_trip() {
        for (name, text) in fixtures("valid") {
            let message = decode(&text).unwrap_or_else(|e| panic!("{name}: {e}"));
            let original: Value = serde_json::from_str(&text).unwrap();
            let encoded: Value = serde_json::from_str(&encode(&message).unwrap()).unwrap();
            if name == "payload_unknown_field.json" {
                // Unknown payload fields are accepted; EmptyPayload keeps them.
                assert_eq!(encoded["payload"]["added_in_future"], true);
            }
            assert_eq!(encoded, original, "{name}: round trip changed the message");
        }
    }

    #[test]
    fn invalid_fixtures_are_rejected() {
        for (name, text) in fixtures("invalid") {
            assert!(decode(&text).is_err(), "{name} was accepted");
        }
    }

    #[test]
    fn type_decides_the_variant() {
        let text =
            r#"{"v":1,"type":"pong","id":"8b2c3d4e-5f6a-4b7c-9d8e-0f1a2b3c4d5e","payload":{}}"#;
        assert!(matches!(decode(text).unwrap(), Message::Pong(_)));
        let swapped = text.replace("\"pong\"", "\"ping\"");
        assert!(matches!(decode(&swapped).unwrap(), Message::Ping(_)));
    }

    #[test]
    fn constructed_messages_decode() {
        for message in [
            hello("0.1.0-beta.1").unwrap(),
            ping().unwrap(),
            shutdown(ShutdownPayloadReason::AppExit).unwrap(),
        ] {
            let text = encode(&message).unwrap();
            let back = decode(&text).unwrap();
            assert_eq!(back.version(), PROTOCOL_VERSION);
            assert_eq!(encode(&back).unwrap(), text);
        }
    }
}
