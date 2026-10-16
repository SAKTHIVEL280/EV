//! The Settings window (docs/FEATURES.md F-410): one instance, focused when
//! opened again. Mica (CLAUDE.md §6.5) is applied in the Windows design pass.

use tauri::{AppHandle, Manager, Runtime, WebviewUrl, WebviewWindowBuilder};

pub const LABEL: &str = "settings";

/// # Errors
/// When the window cannot be created or focused.
pub fn open<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    if let Some(window) = app.get_webview_window(LABEL) {
        window.unminimize()?;
        window.show()?;
        return window.set_focus();
    }
    WebviewWindowBuilder::new(app, LABEL, WebviewUrl::App("index.html".into()))
        .title("EV Settings")
        .inner_size(880.0, 600.0)
        .min_inner_size(720.0, 480.0)
        .center()
        .focused(true)
        .build()?;
    Ok(())
}
