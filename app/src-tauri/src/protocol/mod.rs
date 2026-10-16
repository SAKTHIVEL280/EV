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
    EmptyPayload, ErrorMessage, HelloAckMessage, HelloMessage, HelloPayload, PingMessage,
    PongMessage, ProtocolVersion, ShutdownMessage, ShutdownPayload, ShutdownPayloadReason,
};
use serde_json::Value;
use thiserror::Error;

use crate::error::AppError;
use crate::secrets::uuid_v4;

/// Must equal `x-ev-protocol-version` in the schema (enforced by a test).
pub const PROTOCOL_VERSION: u64 = 1;

#[derive(Clone, Debug)]
pub enum Message {
    Hello(HelloMessage),
    HelloAck(HelloAckMessage),
    Ping(PingMessage),
    Pong(PongMessage),
    Error(ErrorMessage),
    Shutdown(ShutdownMessage),
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

impl Message {
    /// Protocol version declared by the sender in the envelope.
    #[must_use]
    pub fn version(&self) -> u64 {
        let v = match self {
            Self::Hello(m) => &m.v,
            Self::HelloAck(m) => &m.v,
            Self::Ping(m) => &m.v,
            Self::Pong(m) => &m.v,
            Self::Error(m) => &m.v,
            Self::Shutdown(m) => &m.v,
        };
        v.0.get()
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
    let invalid = |kind| move |source| DecodeError::Invalid { kind, source };
    Ok(match kind.as_str() {
        "hello" => Message::Hello(serde_json::from_value(value).map_err(invalid("hello"))?),
        "hello.ack" => {
            Message::HelloAck(serde_json::from_value(value).map_err(invalid("hello.ack"))?)
        }
        "ping" => Message::Ping(serde_json::from_value(value).map_err(invalid("ping"))?),
        "pong" => Message::Pong(serde_json::from_value(value).map_err(invalid("pong"))?),
        "error" => Message::Error(serde_json::from_value(value).map_err(invalid("error"))?),
        "shutdown" => {
            Message::Shutdown(serde_json::from_value(value).map_err(invalid("shutdown"))?)
        }
        _ => return Err(DecodeError::UnknownType(kind)),
    })
}

/// Serialize one message to a WebSocket text frame.
///
/// # Errors
/// Never in practice: every generated type serializes to JSON.
pub fn encode(message: &Message) -> Result<String, serde_json::Error> {
    match message {
        Message::Hello(m) => serde_json::to_string(m),
        Message::HelloAck(m) => serde_json::to_string(m),
        Message::Ping(m) => serde_json::to_string(m),
        Message::Pong(m) => serde_json::to_string(m),
        Message::Error(m) => serde_json::to_string(m),
        Message::Shutdown(m) => serde_json::to_string(m),
    }
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
    Ok(Message::Hello(HelloMessage {
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
    Ok(Message::Ping(PingMessage {
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
    Ok(Message::Shutdown(ShutdownMessage {
        id: id()?,
        payload: ShutdownPayload { reason },
        reply_to: None,
        type_: "shutdown".into(),
        v: version(),
    }))
}

#[cfg(test)]
mod tests {
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
