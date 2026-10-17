//! Windows fullscreen detection (docs/ARCHITECTURE.md §5.1, spike S1).
//!
//! 1. `SHQueryUserNotificationState`: busy (fullscreen app), D3D exclusive
//!    fullscreen, or presentation mode.
//! 2. Borderless fullscreen windows (most modern games, video players) are
//!    not always reported by (1), so also check whether the foreground window
//!    exactly covers its monitor. The desktop and shell windows are excluded.

use std::mem::size_of;

use windows_sys::Win32::Foundation::{HWND, RECT};
use windows_sys::Win32::Graphics::Gdi::{
    GetMonitorInfoW, MONITOR_DEFAULTTONULL, MONITORINFO, MonitorFromWindow,
};
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
    GetAsyncKeyState, GetKeyboardLayoutList, HKL, VK_LBUTTON, VK_MBUTTON, VK_RBUTTON,
};
use windows_sys::Win32::UI::Shell::{
    QUERY_USER_NOTIFICATION_STATE, QUNS_BUSY, QUNS_PRESENTATION_MODE, QUNS_RUNNING_D3D_FULL_SCREEN,
    SHQueryUserNotificationState,
};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    GetClassNameW, GetDesktopWindow, GetForegroundWindow, GetShellWindow, GetWindowRect,
};

/// Physical button state (also correct with swapped buttons, since all three are checked).
pub fn pointer_button_down() -> bool {
    [VK_LBUTTON, VK_RBUTTON, VK_MBUTTON].into_iter().any(|key| {
        // SAFETY: GetAsyncKeyState takes a virtual-key code and has no other preconditions.
        let state = unsafe { GetAsyncKeyState(i32::from(key)) };
        // The high bit (sign) set means the key is down.
        state < 0
    })
}

pub fn fullscreen_active() -> bool {
    notification_state_busy() || foreground_covers_monitor()
}

fn notification_state_busy() -> bool {
    let mut state: QUERY_USER_NOTIFICATION_STATE = 0;
    // SAFETY: `state` is a valid, writable QUERY_USER_NOTIFICATION_STATE.
    let hr = unsafe { SHQueryUserNotificationState(&raw mut state) };
    hr == 0
        && matches!(
            state,
            QUNS_BUSY | QUNS_RUNNING_D3D_FULL_SCREEN | QUNS_PRESENTATION_MODE
        )
}

fn foreground_covers_monitor() -> bool {
    // SAFETY: these functions take no arguments and return window handles (possibly null).
    let (fg, shell, desktop) =
        unsafe { (GetForegroundWindow(), GetShellWindow(), GetDesktopWindow()) };
    if fg.is_null() || fg == shell || fg == desktop || is_desktop_class(fg) {
        return false;
    }
    let mut rect = RECT {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
    };
    // SAFETY: `fg` is a window handle from the OS and `rect` is writable.
    if unsafe { GetWindowRect(fg, &raw mut rect) } == 0 {
        return false;
    }
    // SAFETY: `fg` is a window handle from the OS.
    let monitor = unsafe { MonitorFromWindow(fg, MONITOR_DEFAULTTONULL) };
    if monitor.is_null() {
        return false;
    }
    let mut info = MONITORINFO {
        cbSize: u32::try_from(size_of::<MONITORINFO>()).unwrap_or(0),
        rcMonitor: RECT {
            left: 0,
            top: 0,
            right: 0,
            bottom: 0,
        },
        rcWork: RECT {
            left: 0,
            top: 0,
            right: 0,
            bottom: 0,
        },
        dwFlags: 0,
    };
    // SAFETY: `monitor` is a valid HMONITOR and `info.cbSize` is set as required.
    if unsafe { GetMonitorInfoW(monitor, &raw mut info) } == 0 {
        return false;
    }
    let m = info.rcMonitor;
    rect.left <= m.left && rect.top <= m.top && rect.right >= m.right && rect.bottom >= m.bottom
}

/// Desktop wallpaper hosts (`Progman`, `WorkerW`) cover the monitor but are not apps.
fn is_desktop_class(hwnd: HWND) -> bool {
    let mut buf = [0_u16; 32];
    // SAFETY: `buf` is writable for its full length, which is passed as the limit.
    let len = unsafe {
        GetClassNameW(
            hwnd,
            buf.as_mut_ptr(),
            i32::try_from(buf.len()).unwrap_or(0),
        )
    };
    let Ok(len) = usize::try_from(len) else {
        return false;
    };
    let name = String::from_utf16_lossy(&buf[..len.min(buf.len())]);
    name == "Progman" || name == "WorkerW"
}

/// Language ids (low word of each HKL) of the installed keyboard layouts.
pub fn installed_layout_languages() -> Vec<u16> {
    // SAFETY: a null buffer with size 0 asks only for the count.
    let count = unsafe { GetKeyboardLayoutList(0, std::ptr::null_mut()) };
    let Ok(len) = usize::try_from(count) else {
        return Vec::new();
    };
    let mut layouts: Vec<HKL> = vec![std::ptr::null_mut(); len];
    // SAFETY: `layouts` has room for `count` handles.
    let written = unsafe { GetKeyboardLayoutList(count, layouts.as_mut_ptr()) };
    let written = usize::try_from(written).unwrap_or(0).min(len);
    layouts[..written]
        .iter()
        .map(|hkl| u16::try_from((*hkl as usize) & 0xffff).unwrap_or(0))
        .collect()
}
