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
