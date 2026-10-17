//! Model list for the UI, converted from core's `models.state` message
//! (docs/FEATURES.md F-403).
//!
//! Sizes are whole kilobytes (1 kB = 1000 bytes) in `u32`, so the TypeScript
//! types stay plain `number`s (the largest model is about 5.7 million kB).

use serde::Serialize;
use specta::Type;

use crate::protocol::Message;
use crate::protocol::generated::{Bytes, ModelEntry};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
pub struct ModelInfo {
    pub id: String,
    pub name: String,
    pub summary: String,
    /// small | default | large
    pub role: String,
    pub recommended: bool,
    pub file: String,
    pub size_kb: u32,
    /// available | partial | downloading | verifying | installed | failed
    pub state: String,
    pub received_kb: u32,
    pub kb_per_second: u32,
    /// User-facing reason when `state` is failed.
    pub error: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
pub struct ModelsState {
    pub models_dir: String,
    pub models: Vec<ModelInfo>,
}

#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct ModelsChanged(pub ModelsState);

fn kb(bytes: &Bytes) -> u32 {
    u32::try_from(bytes.0 / 1000).unwrap_or(u32::MAX)
}

fn info(entry: ModelEntry) -> ModelInfo {
    ModelInfo {
        id: entry.id.to_string(),
        name: entry.name.to_string(),
        summary: entry.summary.to_string(),
        role: entry.role.to_string(),
        recommended: entry.recommended,
        file: entry.file.to_string(),
        size_kb: kb(&entry.size_bytes),
        state: entry.state.to_string(),
        received_kb: kb(&entry.received_bytes),
        kb_per_second: kb(&entry.bytes_per_second),
        error: entry.error.map(|e| e.to_string()),
    }
}

/// Convert a `models.state` message; `None` for anything else.
#[must_use]
pub fn update(message: Message) -> Option<ModelsState> {
    match message {
        Message::ModelsState(m) => Some(ModelsState {
            models_dir: m.payload.models_dir.to_string(),
            models: m.payload.models.into_iter().map(info).collect(),
        }),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::decode;

    #[test]
    fn converts_models_state() {
        let raw = include_str!("../../../protocol/fixtures/valid/models_state.json");
        let state = update(decode(raw).unwrap_or_else(|e| panic!("{e}"))).unwrap_or_else(|| {
            panic!("not a models.state message");
        });
        assert_eq!(
            state.models_dir,
            "C:\\Users\\me\\AppData\\Roaming\\EV\\models"
        );
        let first = &state.models[0];
        assert_eq!(
            (first.id.as_str(), first.role.as_str(), first.state.as_str()),
            ("qwen3.5-4b", "default", "downloading")
        );
        assert_eq!(
            (first.size_kb, first.received_kb, first.kb_per_second),
            (2_740_937, 1_048, 5_242)
        );
        assert!(first.recommended);
        assert_eq!(first.error, None);
        let failed = &state.models[1];
        assert_eq!(failed.size_kb, 5_680_522);
        assert_eq!(
            failed.error.as_deref(),
            Some("Couldn't reach Hugging Face. Check the connection and try again.")
        );
    }

    #[test]
    fn other_messages_are_ignored() {
        let raw = include_str!("../../../protocol/fixtures/valid/config_get.json");
        assert!(update(decode(raw).unwrap_or_else(|e| panic!("{e}"))).is_none());
    }
}
