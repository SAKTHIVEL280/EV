//! Core status shown in the island and sent to the UI as an event.

use serde::Serialize;
use specta::Type;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
#[serde(tag = "state", rename_all = "snake_case")]
pub enum CoreStatus {
    Starting,
    Running {
        core_version: String,
        modules: Vec<ModuleInfo>,
    },
    Restarting {
        attempt: u32,
        delay_ms: u32,
    },
    Failed {
        message: String,
    },
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
pub struct ModuleInfo {
    pub name: String,
    pub state: String,
    pub detail: Option<String>,
}

#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct CoreStatusChanged(pub CoreStatus);
