//! Pure island geometry: placement and cursor hit-testing. No window APIs here.

use serde::{Deserialize, Serialize};
use specta::Type;

/// Interactive rectangle reported by the UI, in whole logical (CSS) pixels
/// relative to the island window's top-left corner (the UI rounds outward).
/// Integers keep the generated TypeScript type free of `null` (JSON has no NaN).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize, Type)]
pub struct HitRect {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

/// A rectangle in physical desktop pixels.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PhysRect {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

/// Window position that centers `window_width` horizontally at the top of `work_area`.
#[must_use]
pub fn top_center(work_area: PhysRect, window_width: u32) -> (i32, i32) {
    let spare = i64::from(work_area.width) - i64::from(window_width);
    let x = i64::from(work_area.x) + spare / 2;
    (i32::try_from(x).unwrap_or(work_area.x), work_area.y)
}

/// Whether the cursor (physical desktop coordinates) is inside `rect`.
#[must_use]
pub fn cursor_inside(
    cursor: (f64, f64),
    window_origin: (i32, i32),
    scale: f64,
    rect: HitRect,
) -> bool {
    if scale <= 0.0 || rect.width <= 0 || rect.height <= 0 {
        return false;
    }
    let lx = (cursor.0 - f64::from(window_origin.0)) / scale;
    let ly = (cursor.1 - f64::from(window_origin.1)) / scale;
    let (x, y) = (f64::from(rect.x), f64::from(rect.y));
    lx >= x && lx < x + f64::from(rect.width) && ly >= y && ly < y + f64::from(rect.height)
}

/// Whether the cursor is within `margin` physical pixels of the window bounds.
/// Used to poll fast only when the cursor is close.
#[must_use]
pub fn cursor_near(cursor: (f64, f64), window: PhysRect, margin: f64) -> bool {
    let left = f64::from(window.x) - margin;
    let top = f64::from(window.y) - margin;
    let right = f64::from(window.x) + f64::from(window.width) + margin;
    let bottom = f64::from(window.y) + f64::from(window.height) + margin;
    cursor.0 >= left && cursor.0 < right && cursor.1 >= top && cursor.1 < bottom
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn centers_on_work_area() {
        let wa = PhysRect {
            x: 0,
            y: 0,
            width: 1920,
            height: 1040,
        };
        assert_eq!(top_center(wa, 420), (750, 0));
        // Secondary monitor to the left, with a top taskbar.
        let wa = PhysRect {
            x: -2560,
            y: 48,
            width: 2560,
            height: 1392,
        };
        assert_eq!(top_center(wa, 630), (-2560 + 965, 48));
    }

    #[test]
    fn hit_test_respects_scale_and_origin() {
        let rect = HitRect {
            x: 150,
            y: 0,
            width: 120,
            height: 14,
        };
        // 150% DPI, window at (1000, 0): logical x 150..270 => physical 1225..1405.
        assert!(cursor_inside((1225.0, 0.0), (1000, 0), 1.5, rect));
        assert!(cursor_inside((1404.0, 20.0), (1000, 0), 1.5, rect));
        assert!(!cursor_inside((1405.5, 0.0), (1000, 0), 1.5, rect));
        assert!(!cursor_inside((1300.0, 21.0), (1000, 0), 1.5, rect));
        assert!(!cursor_inside((1224.0, 0.0), (1000, 0), 1.5, rect));
    }

    #[test]
    fn empty_rect_or_bad_scale_never_hits() {
        assert!(!cursor_inside((0.0, 0.0), (0, 0), 1.0, HitRect::default()));
        let rect = HitRect {
            x: 0,
            y: 0,
            width: 10,
            height: 10,
        };
        assert!(!cursor_inside((1.0, 1.0), (0, 0), 0.0, rect));
    }

    #[test]
    fn near_uses_margin() {
        let w = PhysRect {
            x: 100,
            y: 0,
            width: 200,
            height: 100,
        };
        assert!(cursor_near((50.0, 50.0), w, 64.0));
        assert!(!cursor_near((30.0, 50.0), w, 64.0));
        assert!(cursor_near((200.0, 163.0), w, 64.0));
        assert!(!cursor_near((200.0, 164.0), w, 64.0));
    }
}
