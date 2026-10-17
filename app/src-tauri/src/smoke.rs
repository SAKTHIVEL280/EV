//! End-to-end smoke test (`EV_SMOKE_TEST=1`), run by CI on Linux and Windows.
//!
//! The real app starts, core connects, and the island opens the Settings
//! window through the same command as the Settings button. The Settings UI
//! reports when it has rendered core's settings; the app then exits with 0.
//! A watchdog exits with a failure code if that never happens, so a hang
//! (like the Windows window-creation deadlock) fails CI instead of passing.

use std::time::Duration;

use tauri::{AppHandle, Runtime};

pub const ENV: &str = "EV_SMOKE_TEST";
/// Exit code when the smoke test does not finish in time.
pub const TIMEOUT_EXIT_CODE: i32 = 3;
const TIMEOUT: Duration = Duration::from_secs(120);
const FINAL_STEP: &str = "settings-rendered";

#[must_use]
pub fn enabled() -> bool {
    std::env::var_os(ENV).is_some_and(|v| v == "1")
}

/// Exit with [`TIMEOUT_EXIT_CODE`] unless the test finishes first.
pub fn start_watchdog() {
    std::thread::spawn(|| {
        std::thread::sleep(TIMEOUT);
        tracing::error!(timeout_s = TIMEOUT.as_secs(), "smoke test timed out");
        std::process::exit(TIMEOUT_EXIT_CODE);
    });
}

pub fn step<R: Runtime>(app: &AppHandle<R>, step: &str) {
    if !enabled() {
        return;
    }
    tracing::info!(step, "smoke test step");
    if step == FINAL_STEP {
        tracing::info!("smoke test passed");
        app.exit(0);
    }
}
