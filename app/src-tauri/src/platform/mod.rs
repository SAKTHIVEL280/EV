//! OS integration behind small functions; Windows implementations plus
//! development fallbacks so the app runs end-to-end on Linux.

#[cfg(windows)]
mod windows;

/// Whether a fullscreen app, game or presentation is in the foreground.
#[must_use]
pub fn fullscreen_active() -> bool {
    #[cfg(windows)]
    {
        windows::fullscreen_active()
    }
    #[cfg(not(windows))]
    {
        false
    }
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
