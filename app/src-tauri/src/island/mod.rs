//! The island window (CLAUDE.md §6.1, docs/ARCHITECTURE.md §5.1, spike S1).
//!
//! One transparent, undecorated, always-on-top window sized to the largest
//! panel, placed top-center. It never takes focus unless the panel is opened.
//! A cursor loop compares the global cursor with the shape the UI reports and
//! toggles `set_ignore_cursor_events`; the rules are in [`pointer`].

pub mod geometry;
pub mod pointer;

use std::sync::Mutex;
use std::time::Duration;

use serde::Serialize;
use specta::Type;
use tauri::{
    AppHandle, Manager, PhysicalPosition, Runtime, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};
use tauri_specta::Event;

use crate::platform;
use geometry::{HitRect, PhysRect, cursor_distance, cursor_near, top_center};
use pointer::{Reveal, Sample, Tracker};

pub const LABEL: &str = "island";
/// Largest panel plus room for spring overshoot, logical px.
pub const WINDOW_WIDTH: f64 = 420.0;
pub const WINDOW_HEIGHT: f64 = 300.0;

const NEAR_MARGIN_LOGICAL: f64 = 64.0;
const POLL_NEAR: Duration = Duration::from_millis(16);
const POLL_FAR: Duration = Duration::from_millis(100);
const FULLSCREEN_POLL: Duration = Duration::from_secs(1);

/// The shape the UI shows and how the drop reveals; shared with the cursor loop.
#[derive(Clone, Copy, Debug, Default)]
pub struct Shape {
    pub rect: HitRect,
    /// Hover or panel (takes clicks); `false` for the idle drop (never does).
    pub clickable: bool,
}

#[derive(Debug, Default)]
pub struct IslandState {
    shape: Mutex<Shape>,
    reveal: Mutex<Reveal>,
}

impl IslandState {
    #[must_use]
    pub fn shape(&self) -> Shape {
        *self
            .shape
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    pub fn set_shape(&self, shape: Shape) {
        *self
            .shape
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = shape;
    }

    #[must_use]
    pub fn reveal(&self) -> Reveal {
        *self
            .reveal
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    pub fn set_reveal(&self, reveal: Reveal) {
        *self
            .reveal
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = reveal;
    }
}

/// The pointer revealed the drop (`inside`) or left the open shape. The UI
/// cannot see this itself while the window ignores cursor events.
#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct IslandPointer {
    pub inside: bool,
}

/// The island was hidden or shown because a fullscreen app started or stopped.
#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct IslandVisibility {
    pub hidden: bool,
}

/// Create the island window, place it, show it without activation and start
/// the cursor and fullscreen loops.
///
/// # Errors
/// When the window cannot be created or placed.
pub fn create<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<WebviewWindow<R>> {
    let window = WebviewWindowBuilder::new(app, LABEL, WebviewUrl::App("index.html".into()))
        .title("EV")
        .inner_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .focusable(false)
        .focused(false)
        .visible(false)
        .build()?;

    place(&window)?;
    // Show before ignoring cursor events: on Linux the native window only
    // exists once shown, and tao unwraps it when setting the input region.
    window.show()?;
    window.set_ignore_cursor_events(true)?;

    tauri::async_runtime::spawn(cursor_loop(window.clone()));
    if cfg!(windows) {
        tauri::async_runtime::spawn(fullscreen_loop(window.clone()));
    }
    Ok(window)
}

/// Top-center of the primary display's work area.
fn place<R: Runtime>(window: &WebviewWindow<R>) -> tauri::Result<()> {
    // Wayland has no primary monitor; fall back to the current, then the first.
    let monitor = match window.primary_monitor()? {
        Some(m) => Some(m),
        None => match window.current_monitor()? {
            Some(m) => Some(m),
            None => window.available_monitors()?.into_iter().next(),
        },
    };
    let Some(monitor) = monitor else {
        tracing::warn!("no monitor found; island left at default position");
        return Ok(());
    };
    let area = monitor.work_area();
    let work_area = PhysRect {
        x: area.position.x,
        y: area.position.y,
        width: area.size.width,
        height: area.size.height,
    };
    // Computed from the logical size: before the first paint some platforms
    // (Wayland) report an outer size of 0x0.
    let scale = monitor.scale_factor();
    let width = physical(WINDOW_WIDTH * scale);
    let (x, y) = top_center(work_area, width);
    window.set_position(PhysicalPosition::new(x, y))?;
    tracing::info!(x, y, width, scale, "island placed");
    Ok(())
}

fn physical(logical_px: f64) -> u32 {
    // Window sizes are small positive values; the cast cannot truncate meaningfully.
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    let px = logical_px.round().max(0.0) as u32;
    px
}

async fn cursor_loop<R: Runtime>(window: WebviewWindow<R>) {
    let mut tracker = Tracker::default();
    let mut interactive = false;
    loop {
        let state = window.state::<IslandState>();
        let shape = state.shape();
        let (distance, near) = match sample(&window, shape.rect) {
            Ok(sampled) => sampled,
            Err(e) => {
                // e.g. Wayland exposes no global cursor: keep the window usable.
                tracing::warn!(error = %e, "cursor position unavailable; island stays interactive");
                if let Err(e) = window.set_ignore_cursor_events(false) {
                    tracing::warn!(error = %e, "could not make island interactive");
                }
                return;
            }
        };
        let decision = tracker.update(
            Sample {
                distance,
                clickable: shape.clickable,
                button_down: platform::pointer_button_down(),
                now: std::time::Instant::now(),
            },
            state.reveal(),
        );
        if decision.interactive != interactive {
            interactive = decision.interactive;
            if let Err(e) = window.set_ignore_cursor_events(!interactive) {
                tracing::warn!(error = %e, "set_ignore_cursor_events failed");
            }
        }
        if let Some(inside) = decision.pointer
            && let Err(e) = (IslandPointer { inside }).emit(&window)
        {
            tracing::warn!(error = %e, "emit IslandPointer failed");
        }
        tokio::time::sleep(if near { POLL_NEAR } else { POLL_FAR }).await;
    }
}

/// Distance from the cursor to `rect` (logical px) and whether the cursor is
/// close to the window at all (poll faster then).
fn sample<R: Runtime>(
    window: &WebviewWindow<R>,
    rect: HitRect,
) -> tauri::Result<(Option<f64>, bool)> {
    let cursor = window.cursor_position()?;
    let origin = window.outer_position()?;
    let size = window.outer_size()?;
    let scale = window.scale_factor()?;
    let cursor = (cursor.x, cursor.y);
    let bounds = PhysRect {
        x: origin.x,
        y: origin.y,
        width: size.width,
        height: size.height,
    };
    Ok((
        cursor_distance(cursor, (origin.x, origin.y), scale, rect),
        cursor_near(cursor, bounds, NEAR_MARGIN_LOGICAL * scale),
    ))
}

async fn fullscreen_loop<R: Runtime>(window: WebviewWindow<R>) {
    let mut hidden = false;
    loop {
        tokio::time::sleep(FULLSCREEN_POLL).await;
        let now = platform::fullscreen_active();
        if now == hidden {
            continue;
        }
        hidden = now;
        let result = if hidden { window.hide() } else { window.show() };
        if let Err(e) = result {
            tracing::warn!(error = %e, hidden, "island visibility change failed");
        }
        tracing::info!(hidden, "fullscreen state changed");
        if let Err(e) = (IslandVisibility { hidden }).emit(&window) {
            tracing::warn!(error = %e, "emit IslandVisibility failed");
        }
    }
}
