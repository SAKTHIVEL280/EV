//! Voice messages for the island (docs/FEATURES.md F-005, F-008): mic and
//! speech state, the live mic level and the words heard.

use serde::Serialize;
use specta::Type;

use crate::protocol::Message;

#[derive(Clone, Debug, PartialEq, Serialize, Type)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum VoiceUpdateKind {
    State {
        /// The microphone is open: the island shows the mic indicator.
        mic: bool,
        speaking: bool,
        /// Why voice stopped or couldn't start, in plain words.
        message: Option<String>,
        /// `not_installed`, `no_mic`, `mic_blocked`, `no_speaker`, `failed`, `no_speech` or `off`.
        code: Option<String>,
    },
    /// Mic level 0..1, about 15 times a second while the mic is open.
    Level { level: f32 },
    /// Words recognized so far; `is_final` once the user stopped talking.
    Heard { text: String, is_final: bool },
}

#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct VoiceUpdate(pub VoiceUpdateKind);

/// Where a listening request came from.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Deserialize, Type)]
#[serde(rename_all = "snake_case")]
pub enum VoiceSource {
    Hotkey,
    Button,
    PushToTalk,
}

/// Why the app stops voice (see `voice.stop` in the protocol).
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Deserialize, Type)]
#[serde(rename_all = "snake_case")]
pub enum VoiceStopReason {
    Typing,
    Closed,
    Button,
    Send,
    Silence,
}

/// Convert a voice message; `None` for anything else.
#[must_use]
pub fn update(message: Message) -> Option<VoiceUpdateKind> {
    Some(match message {
        Message::VoiceState(m) => VoiceUpdateKind::State {
            mic: m.payload.mic,
            speaking: m.payload.speaking,
            message: m.payload.message.map(|t| t.to_string()),
            code: m.payload.code.map(|c| c.to_string()),
        },
        #[expect(clippy::cast_possible_truncation, reason = "a 0..1 level fits f32")]
        Message::VoiceLevel(m) => VoiceUpdateKind::Level {
            level: m.payload.level as f32,
        },
        Message::VoiceHeard(m) => VoiceUpdateKind::Heard {
            text: m.payload.text.to_string(),
            is_final: m.payload.final_,
        },
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

    #[test]
    fn converts_every_voice_message() {
        assert_eq!(
            update(fixture("voice_state.json")),
            Some(VoiceUpdateKind::State {
                mic: true,
                speaking: false,
                message: None,
                code: None,
            })
        );
        assert_eq!(
            update(fixture("voice_state_message.json")),
            Some(VoiceUpdateKind::State {
                mic: false,
                speaking: false,
                message: Some("No microphone found.".into()),
                code: Some("no_mic".into()),
            })
        );
        assert_eq!(
            update(fixture("voice_level.json")),
            Some(VoiceUpdateKind::Level { level: 0.42 })
        );
        assert_eq!(
            update(fixture("voice_heard.json")),
            Some(VoiceUpdateKind::Heard {
                text: "open notepad".into(),
                is_final: true,
            })
        );
        assert_eq!(update(fixture("ping.json")), None);
    }
}
