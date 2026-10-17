//! OS integration behind small functions; Windows implementations plus
//! development fallbacks so the app runs end-to-end on Linux.

#[cfg(windows)]
mod windows;

/// Why the island should hide right now (a fullscreen app, game or
/// presentation is in front), or `None`. The reason goes to the log.
#[must_use]
pub fn fullscreen() -> Option<String> {
    #[cfg(windows)]
    {
        windows::fullscreen_reason()
    }
    #[cfg(not(windows))]
    {
        None
    }
}

/// What Windows says about the foreground window.
#[derive(Clone, Debug)]
pub struct Foreground {
    pub class: String,
    pub style: u32,
    pub ex_style: u32,
    /// It is the shell window or the desktop window itself.
    pub is_shell_or_desktop: bool,
    /// Its rectangle covers its whole monitor (not just the work area).
    pub covers_monitor: bool,
}

/// Shell surfaces that cover the monitor without being a fullscreen app: the
/// desktop (wallpaper), taskbars, Start / Search and Task View hosts.
const SHELL_CLASSES: [&str; 8] = [
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "XamlExplorerHostIslandWindow",
    "Windows.UI.Core.CoreWindow",
    "MultitaskingViewFrame",
    "ForegroundStaging",
];
const WS_DLGFRAME: u32 = 0x0040_0000;
const WS_THICKFRAME: u32 = 0x0004_0000;
const WS_EX_WINDOWEDGE: u32 = 0x0000_0100;
const WS_EX_TOOLWINDOW: u32 = 0x0000_0080;

/// The fullscreen rule, after Chromium's `fullscreen_win.cc`:
/// - Windows' notification state counts only for exclusive (D3D) fullscreen
///   and presentation mode. "Busy" does not: Windows also reports it while the
///   desktop is in front, which hid the island there (beta test 2026-10-17).
/// - Otherwise the foreground window must cover its whole monitor, have no
///   frame (dialog or resizable), not be a tool window, and not be the shell.
#[must_use]
pub fn fullscreen_reason(
    notification: Option<&str>,
    foreground: Option<&Foreground>,
) -> Option<String> {
    if let Some(state @ ("d3d_fullscreen" | "presentation")) = notification {
        return Some(state.to_owned());
    }
    let fg = foreground?;
    let framed = fg.style & (WS_DLGFRAME | WS_THICKFRAME) != 0
        || fg.ex_style & (WS_EX_WINDOWEDGE | WS_EX_TOOLWINDOW) != 0;
    let shell = fg.is_shell_or_desktop || SHELL_CLASSES.contains(&fg.class.as_str());
    (fg.covers_monitor && !framed && !shell).then(|| format!("window {}", fg.class))
}

/// Before the island panel takes keyboard focus: remember which window had it.
/// `own` is the island's window handle. Linux development: no-op.
pub fn remember_foreground(own: isize) {
    #[cfg(windows)]
    windows::remember_foreground(own);
    #[cfg(not(windows))]
    let _ = own;
}

/// After the panel closes while focused: hand keyboard focus back to the
/// remembered window. `false` when there was none. Linux development: `false`.
#[must_use]
pub fn restore_foreground() -> bool {
    #[cfg(windows)]
    {
        windows::restore_foreground()
    }
    #[cfg(not(windows))]
    {
        false
    }
}

/// Whether a mouse button is held (e.g. dragging a browser tab). The island
/// does not reveal meanwhile. Linux development: always `false`.
#[must_use]
pub fn pointer_button_down() -> bool {
    #[cfg(windows)]
    {
        windows::pointer_button_down()
    }
    #[cfg(not(windows))]
    {
        false
    }
}

/// Whether a Chinese, Japanese or Korean keyboard layout (input method) is
/// installed; Ctrl+Space toggles some of those input methods (F-004).
#[must_use]
pub fn cjk_input_installed() -> bool {
    #[cfg(windows)]
    {
        windows::installed_layout_languages()
            .into_iter()
            .any(is_cjk_layout)
    }
    #[cfg(not(windows))]
    {
        false
    }
}

/// `language_id` is the low word of a keyboard layout handle (a LANGID).
#[must_use]
pub fn is_cjk_layout(language_id: u16) -> bool {
    const LANG_CHINESE: u16 = 0x04;
    const LANG_JAPANESE: u16 = 0x11;
    const LANG_KOREAN: u16 = 0x12;
    matches!(
        language_id & 0x03ff,
        LANG_CHINESE | LANG_JAPANESE | LANG_KOREAN
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn window(class: &str, covers_monitor: bool) -> Foreground {
        Foreground {
            class: class.into(),
            style: 0x1600_0000, // WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS: borderless
            ex_style: 0,
            is_shell_or_desktop: false,
            covers_monitor,
        }
    }

    #[test]
    fn desktop_and_shell_never_count() {
        for class in [
            "Progman",
            "WorkerW",
            "Shell_TrayWnd",
            "XamlExplorerHostIslandWindow",
        ] {
            assert_eq!(
                fullscreen_reason(None, Some(&window(class, true))),
                None,
                "{class}"
            );
        }
        let shell = Foreground {
            is_shell_or_desktop: true,
            ..window("SomethingNew", true)
        };
        assert_eq!(fullscreen_reason(None, Some(&shell)), None);
    }

    #[test]
    fn busy_alone_is_not_fullscreen() {
        // Windows reports "busy" with the desktop in front (beta test 2026-10-17).
        assert_eq!(
            fullscreen_reason(Some("busy"), Some(&window("Progman", true))),
            None
        );
        assert_eq!(fullscreen_reason(Some("busy"), None), None);
    }

    #[test]
    fn exclusive_fullscreen_and_presentations_count() {
        assert_eq!(
            fullscreen_reason(Some("d3d_fullscreen"), None).as_deref(),
            Some("d3d_fullscreen")
        );
        assert_eq!(
            fullscreen_reason(Some("presentation"), None).as_deref(),
            Some("presentation")
        );
    }

    #[test]
    fn borderless_window_covering_the_monitor_counts() {
        let video = window("Chrome_WidgetWin_1", true);
        assert_eq!(
            fullscreen_reason(Some("other"), Some(&video)).as_deref(),
            Some("window Chrome_WidgetWin_1")
        );
        assert_eq!(fullscreen_reason(None, Some(&window("Game", false))), None);
    }

    #[test]
    fn framed_and_tool_windows_dont_count() {
        let maximized = Foreground {
            style: 0x16CF_0000, // WS_OVERLAPPEDWINDOW | WS_MAXIMIZE | WS_VISIBLE
            ..window("Notepad", true)
        };
        assert_eq!(fullscreen_reason(None, Some(&maximized)), None);
        let tool = Foreground {
            ex_style: WS_EX_TOOLWINDOW,
            ..window("Overlay", true)
        };
        assert_eq!(fullscreen_reason(None, Some(&tool)), None);
    }

    #[test]
    fn cjk_languages_detected() {
        assert!(is_cjk_layout(0x0804)); // zh-CN
        assert!(is_cjk_layout(0x0404)); // zh-TW
        assert!(is_cjk_layout(0x0411)); // ja-JP
        assert!(is_cjk_layout(0x0412)); // ko-KR
        assert!(!is_cjk_layout(0x0409)); // en-US
        assert!(!is_cjk_layout(0x0439)); // hi-IN
    }
}
