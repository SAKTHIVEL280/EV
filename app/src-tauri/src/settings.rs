//! Settings types for the UI, converted from core's `config.state` and
//! `config.rejected` messages (docs/FEATURES.md F-410).

use serde::{Deserialize, Serialize};
use specta::Type;

use crate::protocol::Message;
use crate::protocol::generated;

/// A setting value. Integers are `i32` so the TypeScript type stays `number`.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, Type)]
#[serde(untagged)]
pub enum SettingValue {
    Bool(bool),
    Int(i32),
    Text(String),
}

impl From<generated::SettingValue> for SettingValue {
    fn from(value: generated::SettingValue) -> Self {
        match value {
            generated::SettingValue::Boolean(b) => Self::Bool(b),
            generated::SettingValue::Integer(i) => Self::Int(clamp(i)),
            generated::SettingValue::String(s) => Self::Text(s),
        }
    }
}

impl From<SettingValue> for generated::SettingValue {
    fn from(value: SettingValue) -> Self {
        match value {
            SettingValue::Bool(b) => Self::Boolean(b),
            SettingValue::Int(i) => Self::Integer(i64::from(i)),
            SettingValue::Text(s) => Self::String(s),
        }
    }
}

fn clamp(value: i64) -> i32 {
    i32::try_from(value).unwrap_or(if value < 0 { i32::MIN } else { i32::MAX })
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
pub struct SettingItem {
    pub section: String,
    pub key: String,
    /// Settings section id (general, models, … about).
    pub nav: String,
    pub label: String,
    pub description: String,
    /// boolean | choice | integer | text
    pub kind: String,
    pub default: SettingValue,
    pub value: SettingValue,
    pub options: Vec<String>,
    pub minimum: Option<i32>,
    pub maximum: Option<i32>,
    /// Shown after integer values (px, ms, min, tokens).
    pub unit: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
pub struct ConfigWarning {
    pub key: String,
    pub message: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
pub struct SettingsState {
    pub path: String,
    pub items: Vec<SettingItem>,
    pub warnings: Vec<ConfigWarning>,
}

#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct SettingsChanged(pub SettingsState);

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type, tauri_specta::Event)]
pub struct SettingRejected {
    pub section: String,
    pub key: String,
    pub message: String,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Update {
    State(SettingsState),
    Rejected(SettingRejected),
}

/// Convert a settings message; `None` for anything else.
#[must_use]
pub fn update(message: Message) -> Option<Update> {
    match message {
        Message::ConfigState(m) => Some(Update::State(SettingsState {
            path: m.payload.path.to_string(),
            items: m
                .payload
                .items
                .into_iter()
                .map(|i| SettingItem {
                    section: i.section.to_string(),
                    key: i.key.to_string(),
                    nav: i.nav.to_string(),
                    label: i.label.to_string(),
                    description: i.description.to_string(),
                    kind: i.kind.to_string(),
                    default: i.default.into(),
                    value: i.value.into(),
                    options: i.options.into_iter().map(|o| o.to_string()).collect(),
                    minimum: i.minimum.map(clamp),
                    maximum: i.maximum.map(clamp),
                    unit: i.unit.map(|u| u.to_string()),
                })
                .collect(),
            warnings: m
                .payload
                .warnings
                .into_iter()
                .map(|w| ConfigWarning {
                    key: w.key.to_string(),
                    message: w.message.to_string(),
                })
                .collect(),
        })),
        Message::ConfigRejected(m) => Some(Update::Rejected(SettingRejected {
            section: m.payload.section.to_string(),
            key: m.payload.key.to_string(),
            message: m.payload.message.to_string(),
        })),
        _ => None,
    }
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
    fn converts_state() {
        let Some(Update::State(state)) = update(fixture("config_state.json")) else {
            panic!("expected state");
        };
        assert_eq!(state.path, "/home/u/.local/share/EV/config.toml");
        let context = &state.items[0];
        assert_eq!(
            (
                context.section.as_str(),
                context.key.as_str(),
                context.nav.as_str()
            ),
            ("llm", "context", "models")
        );
        assert_eq!(context.kind, "integer");
        assert_eq!(
            (context.default.clone(), context.value.clone()),
            (SettingValue::Int(8192), SettingValue::Int(16384))
        );
        assert_eq!(
            (context.minimum, context.maximum),
            (Some(2048), Some(131_072))
        );
        assert_eq!(context.options.len(), 0);
        assert_eq!(context.unit.as_deref(), Some("tokens"));
        assert_eq!(state.items[1].options, ["instant", "normal", "deep", "max"]);
        assert_eq!(state.items[1].value, SettingValue::Text("deep".into()));
        assert_eq!(state.warnings[0].key, "logging.level");
    }

    #[test]
    fn converts_rejection_and_ignores_others() {
        assert_eq!(
            update(fixture("config_rejected.json")),
            Some(Update::Rejected(SettingRejected {
                section: "llm".into(),
                key: "context".into(),
                message: "That value is not allowed. Use 2048 to 131072.".into(),
            }))
        );
        assert_eq!(update(fixture("ping.json")), None);
    }

    #[test]
    fn values_round_trip_and_clamp() {
        for v in [
            SettingValue::Bool(true),
            SettingValue::Int(-5),
            SettingValue::Text("x".into()),
        ] {
            assert_eq!(
                SettingValue::from(generated::SettingValue::from(v.clone())),
                v
            );
        }
        assert_eq!(
            SettingValue::from(generated::SettingValue::Integer(i64::MAX)),
            SettingValue::Int(i32::MAX)
        );
    }
}
