//! Global shortcut that opens the island panel (docs/FEATURES.md F-004).

use serde::Serialize;
use specta::Type;
use tauri::{AppHandle, Manager, Runtime};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};
use tauri_specta::Event;

use crate::island;
use crate::platform;
use crate::state::AppState;

pub const DEFAULT_SHORTCUT: &str = "Ctrl+Space";
const TAKEN_TEXT: &str = "Another app uses this shortcut. Choose a different one.";
const INVALID_TEXT: &str = "This shortcut can't be used. Choose a different one.";
const IME_TEXT: &str =
    "Ctrl+Space may also switch your input method. If typing is affected, choose Ctrl+Shift+Space.";

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
pub struct HotkeyStatus {
    pub shortcut: String,
    /// active | off | unavailable | invalid
    pub state: String,
    pub detail: Option<String>,
}

#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct HotkeyStatusChanged(pub HotkeyStatus);

/// Ask the island to open the panel, or close it if it is open (hotkey, tray).
#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct IslandToggleRequested;

/// Register `spec` (replacing any earlier shortcut), store and announce the result.
pub fn apply<R: Runtime>(app: &AppHandle<R>, spec: &str) -> HotkeyStatus {
    let status = register(app, spec);
    tracing::info!(shortcut = %status.shortcut, state = %status.state, "hotkey");
    app.state::<AppState>().set_hotkey(status.clone());
    if let Err(e) = HotkeyStatusChanged(status.clone()).emit(app) {
        tracing::warn!(error = %e, "emit HotkeyStatusChanged failed");
    }
    status
}

fn register<R: Runtime>(app: &AppHandle<R>, spec: &str) -> HotkeyStatus {
    let shortcuts = app.global_shortcut();
    if let Err(e) = shortcuts.unregister_all() {
        tracing::warn!(error = %e, "unregister shortcuts failed");
    }
    let spec = spec.trim();
    let status = |state: &str, detail: Option<&str>| HotkeyStatus {
        shortcut: spec.to_owned(),
        state: state.to_owned(),
        detail: detail.map(str::to_owned),
    };
    if spec.is_empty() {
        return status("off", None);
    }
    let Ok(shortcut) = spec.parse::<Shortcut>() else {
        return status("invalid", Some(INVALID_TEXT));
    };
    let result = shortcuts.on_shortcut(shortcut, |app, _shortcut, event| {
        if event.state == ShortcutState::Pressed {
            request_toggle(app);
        }
    });
    match result {
        Ok(()) if is_ctrl_space(spec) && platform::cjk_input_installed() => {
            status("active", Some(IME_TEXT))
        }
        Ok(()) => status("active", None),
        Err(e) => {
            tracing::warn!(error = %e, "shortcut not registered");
            status("unavailable", Some(TAKEN_TEXT))
        }
    }
}

/// Toggle the island panel (hotkey and tray share this).
pub fn request_toggle<R: Runtime>(app: &AppHandle<R>) {
    if let Some(window) = app.get_webview_window(island::LABEL)
        && let Err(e) = IslandToggleRequested.emit_to(&window, window.label())
    {
        tracing::warn!(error = %e, "emit IslandToggleRequested failed");
    }
}

fn is_ctrl_space(spec: &str) -> bool {
    spec.split('+')
        .map(str::trim)
        .map(str::to_ascii_lowercase)
        .collect::<Vec<_>>()
        == ["ctrl", "space"]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ctrl_space_detection() {
        assert!(is_ctrl_space("Ctrl+Space"));
        assert!(is_ctrl_space("ctrl + space"));
        assert!(!is_ctrl_space("Ctrl+Shift+Space"));
        assert!(!is_ctrl_space("Alt+Space"));
    }

    #[test]
    fn config_format_parses() {
        for spec in [
            "Ctrl+Space",
            "ctrl+shift+space",
            "Alt+F12",
            "Ctrl+Alt+K",
            "Super+1",
        ] {
            assert!(spec.parse::<Shortcut>().is_ok(), "{spec}");
        }
    }
}
