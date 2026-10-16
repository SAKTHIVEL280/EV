//! Chat and model-status types for the UI, converted from core's messages
//! (docs/FEATURES.md F-001, F-003).

use serde::{Deserialize, Serialize};
use specta::Type;

use crate::protocol::Message;
use crate::protocol::generated;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, Type)]
#[serde(rename_all = "lowercase")]
pub enum Effort {
    Instant,
    Normal,
    Deep,
    Max,
}

impl From<Effort> for generated::Effort {
    fn from(effort: Effort) -> Self {
        match effort {
            Effort::Instant => Self::Instant,
            Effort::Normal => Self::Normal,
            Effort::Deep => Self::Deep,
            Effort::Max => Self::Max,
        }
    }
}

impl From<generated::Effort> for Effort {
    fn from(effort: generated::Effort) -> Self {
        match effort {
            generated::Effort::Instant => Self::Instant,
            generated::Effort::Normal => Self::Normal,
            generated::Effort::Deep => Self::Deep,
            generated::Effort::Max => Self::Max,
        }
    }
}

/// One step of a chat turn, in order.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ChatUpdateKind {
    Started {
        turn_id: String,
        effort: Effort,
        model: Option<String>,
    },
    Delta {
        turn_id: String,
        text: String,
    },
    Tool {
        turn_id: String,
        name: String,
        state: String,
    },
    Done {
        turn_id: String,
        text: String,
        effort: Effort,
        model: Option<String>,
        first_token_ms: Option<u32>,
        total_ms: u32,
        cancelled: bool,
    },
    Failed {
        turn_id: String,
        code: String,
        message: String,
    },
}

#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct ChatUpdate(pub ChatUpdateKind);

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
pub struct LlmStatus {
    /// unloaded | loading | ready | failed
    pub state: String,
    pub model: Option<String>,
    pub detail: Option<String>,
}

impl LlmStatus {
    #[must_use]
    pub fn unloaded() -> Self {
        Self {
            state: "unloaded".into(),
            model: None,
            detail: None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct LlmStatusChanged(pub LlmStatus);

/// What a core message means for the UI.
#[derive(Debug, PartialEq, Eq)]
pub enum Update {
    Chat(ChatUpdateKind),
    Llm(LlmStatus),
}

fn millis(value: u64) -> u32 {
    u32::try_from(value).unwrap_or(u32::MAX)
}

/// Convert a chat or model-status message; `None` for anything else.
#[must_use]
pub fn update(message: Message) -> Option<Update> {
    Some(match message {
        Message::ChatStarted(m) => Update::Chat(ChatUpdateKind::Started {
            turn_id: m.payload.turn_id.0.to_string(),
            effort: m.payload.effort.into(),
            model: m.payload.model.map(String::from),
        }),
        Message::ChatDelta(m) => Update::Chat(ChatUpdateKind::Delta {
            turn_id: m.payload.turn_id.0.to_string(),
            text: m.payload.text,
        }),
        Message::ChatTool(m) => Update::Chat(ChatUpdateKind::Tool {
            turn_id: m.payload.turn_id.0.to_string(),
            name: String::from(m.payload.name),
            state: m.payload.state.to_string(),
        }),
        Message::ChatDone(m) => Update::Chat(ChatUpdateKind::Done {
            turn_id: m.payload.turn_id.0.to_string(),
            text: m.payload.text,
            effort: m.payload.effort.into(),
            model: m.payload.model.map(String::from),
            first_token_ms: m.payload.timings.first_token_ms.map(|v| millis(v.0)),
            total_ms: millis(m.payload.timings.total_ms.0),
            cancelled: m.payload.cancelled,
        }),
        Message::ChatFailed(m) => Update::Chat(ChatUpdateKind::Failed {
            turn_id: m.payload.turn_id.0.to_string(),
            code: String::from(m.payload.code),
            message: String::from(m.payload.message),
        }),
        Message::LlmStatus(m) => Update::Llm(LlmStatus {
            state: m.payload.state.to_string(),
            model: m.payload.model.map(String::from),
            detail: m.payload.detail.map(String::from),
        }),
        _ => return None,
    })
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::path::Path;

    use super::*;
    use crate::protocol::decode;

    fn fixture(name: &str) -> Message {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../protocol/fixtures/valid")
            .join(name);
        decode(&fs::read_to_string(path).unwrap()).unwrap()
    }

    const TURN: &str = "36c14c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d";

    #[test]
    fn converts_every_chat_message() {
        assert_eq!(
            update(fixture("chat_started.json")),
            Some(Update::Chat(ChatUpdateKind::Started {
                turn_id: TURN.into(),
                effort: Effort::Max,
                model: Some("Qwen3.5-4B-Q4_K_M.gguf".into()),
            }))
        );
        assert_eq!(
            update(fixture("chat_delta.json")),
            Some(Update::Chat(ChatUpdateKind::Delta {
                turn_id: TURN.into(),
                text: "Here is ".into()
            }))
        );
        assert_eq!(
            update(fixture("chat_tool.json")),
            Some(Update::Chat(ChatUpdateKind::Tool {
                turn_id: TURN.into(),
                name: "current_time".into(),
                state: "done".into(),
            }))
        );
        assert_eq!(
            update(fixture("chat_done.json")),
            Some(Update::Chat(ChatUpdateKind::Done {
                turn_id: TURN.into(),
                text: "Here is your plan.".into(),
                effort: Effort::Max,
                model: Some("Qwen3.5-4B-Q4_K_M.gguf".into()),
                first_token_ms: Some(812),
                total_ms: 4120,
                cancelled: false,
            }))
        );
        assert_eq!(
            update(fixture("chat_failed.json")),
            Some(Update::Chat(ChatUpdateKind::Failed {
                turn_id: TURN.into(),
                code: "no_model".into(),
                message: "No model installed. Add one in Settings.".into(),
            }))
        );
        assert_eq!(
            update(fixture("llm_status.json")),
            Some(Update::Llm(LlmStatus {
                state: "loading".into(),
                model: Some("Qwen3.5-4B-Q4_K_M.gguf".into()),
                detail: None,
            }))
        );
        assert_eq!(update(fixture("ping.json")), None);
    }

    #[test]
    fn effort_round_trips() {
        for e in [Effort::Instant, Effort::Normal, Effort::Deep, Effort::Max] {
            assert_eq!(Effort::from(generated::Effort::from(e)), e);
        }
    }
}
