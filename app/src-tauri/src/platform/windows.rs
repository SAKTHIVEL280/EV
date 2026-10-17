//! Windows calls behind `platform`: fullscreen facts, focus hand-back, mouse
//! buttons, keyboard layouts. The fullscreen rule itself is in `platform`
//! (pure, tested on every OS).

use std::mem::size_of;
use std::sync::atomic::{AtomicIsize, Ordering};

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
    GWL_EXSTYLE, GWL_STYLE, GetClassNameW, GetDesktopWindow, GetForegroundWindow, GetShellWindow,
    GetWindowLongW, GetWindowRect, IsWindow, SetForegroundWindow,
};

/// The window that had keyboard focus before the island panel took it.
static PREVIOUS_FOREGROUND: AtomicIsize = AtomicIsize::new(0);

/// Remember the foreground window unless it is the island (`own`) itself.
pub fn remember_foreground(own: isize) {
    // SAFETY: GetForegroundWindow takes no arguments and may return null.
    let fg = unsafe { GetForegroundWindow() } as isize;
    if fg != 0 && fg != own {
        PREVIOUS_FOREGROUND.store(fg, Ordering::Relaxed);
    }
}

/// Give keyboard focus back to the remembered window. `false` when there is
/// none or it has closed. Allowed because the island is the foreground window.
pub fn restore_foreground() -> bool {
    let previous = PREVIOUS_FOREGROUND.swap(0, Ordering::Relaxed) as HWND;
    // SAFETY: IsWindow accepts any value, including stale or null handles.
    if previous.is_null() || unsafe { IsWindow(previous) } == 0 {
        return false;
    }
    // SAFETY: `previous` is an existing top-level window handle.
    unsafe { SetForegroundWindow(previous) != 0 }
}

/// Physical button state (also correct with swapped buttons, since all three are checked).
pub fn pointer_button_down() -> bool {
    [VK_LBUTTON, VK_RBUTTON, VK_MBUTTON].into_iter().any(|key| {
        // SAFETY: GetAsyncKeyState takes a virtual-key code and has no other preconditions.
        let state = unsafe { GetAsyncKeyState(i32::from(key)) };
        // The high bit (sign) set means the key is down.
        state < 0
    })
}

/// Facts about the foreground window for [`super::fullscreen_reason`].
pub fn fullscreen_reason() -> Option<String> {
    let state = notification_state();
    // SAFETY: these functions take no arguments and return window handles (possibly null).
    let (fg, shell, desktop) =
        unsafe { (GetForegroundWindow(), GetShellWindow(), GetDesktopWindow()) };
    let foreground = (!fg.is_null()).then(|| {
        // SAFETY: `fg` is a window handle from the OS; GetWindowLongW accepts stale handles.
        let (style, ex_style) = unsafe {
            (
                GetWindowLongW(fg, GWL_STYLE),
                GetWindowLongW(fg, GWL_EXSTYLE),
            )
        };
        super::Foreground {
            class: class_name(fg),
            // Styles are bit flags; the sign bit is WS_POPUP, not a sign.
            style: style.cast_unsigned(),
            ex_style: ex_style.cast_unsigned(),
            is_shell_or_desktop: fg == shell || fg == desktop,
            covers_monitor: covers_its_monitor(fg),
        }
    });
    super::fullscreen_reason(state.map(notification_name), foreground.as_ref())
}

fn notification_state() -> Option<QUERY_USER_NOTIFICATION_STATE> {
    let mut state: QUERY_USER_NOTIFICATION_STATE = 0;
    // SAFETY: `state` is a valid, writable QUERY_USER_NOTIFICATION_STATE.
    let hr = unsafe { SHQueryUserNotificationState(&raw mut state) };
    (hr == 0).then_some(state)
}

fn notification_name(state: QUERY_USER_NOTIFICATION_STATE) -> &'static str {
    match state {
        QUNS_RUNNING_D3D_FULL_SCREEN => "d3d_fullscreen",
        QUNS_PRESENTATION_MODE => "presentation",
        QUNS_BUSY => "busy",
        _ => "other",
    }
}

fn covers_its_monitor(fg: HWND) -> bool {
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

fn class_name(hwnd: HWND) -> String {
    let mut buf = [0_u16; 64];
    // SAFETY: `buf` is writable for its full length, which is passed as the limit.
    let len = unsafe {
        GetClassNameW(
            hwnd,
            buf.as_mut_ptr(),
            i32::try_from(buf.len()).unwrap_or(0),
        )
    };
    let len = usize::try_from(len).unwrap_or(0).min(buf.len());
    String::from_utf16_lossy(&buf[..len])
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
