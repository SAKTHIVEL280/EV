//! When the island reacts to the pointer (CLAUDE.md §1.3 "never covers
//! content", §6.1). Pure logic, driven by the cursor loop.
//!
//! - Idle (the drop): never catches clicks. It opens ("reveals") only when the
//!   pointer stays within `reveal.distance` of it for `reveal.delay`, with no
//!   mouse button held (so dragging a browser tab past it does nothing).
//! - Open shapes (hover, panel): catch clicks only inside their rectangle.
//!   The pointer counts as gone once it is `LEAVE_TOLERANCE` px outside.
//!
//! Found in the first Windows test: the old hover area caught clicks meant
//! for the browser tabs under it.

use std::time::{Duration, Instant};

/// How far outside an open shape the pointer may drift before it closes, logical px.
pub const LEAVE_TOLERANCE: f64 = 8.0;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Reveal {
    /// Logical px from the drop.
    pub distance: f64,
    pub delay: Duration,
}

impl Default for Reveal {
    fn default() -> Self {
        Self {
            distance: 6.0,
            delay: Duration::from_millis(150),
        }
    }
}

/// One cursor sample.
#[derive(Clone, Copy, Debug)]
pub struct Sample {
    /// Logical px from the current shape's rectangle; `None` when unknown.
    pub distance: Option<f64>,
    /// The UI's current shape takes clicks (hover or panel), not the idle drop.
    pub clickable: bool,
    pub button_down: bool,
    pub now: Instant,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Decision {
    /// The window should receive mouse input (not click-through).
    pub interactive: bool,
    /// `Some` when the pointer entered (`true`) or left (`false`).
    pub pointer: Option<bool>,
}

#[derive(Debug, Default)]
pub struct Tracker {
    inside: bool,
    near_since: Option<Instant>,
}

impl Tracker {
    pub fn update(&mut self, sample: Sample, reveal: Reveal) -> Decision {
        let distance = sample.distance.unwrap_or(f64::INFINITY);
        let (interactive, inside) = if sample.clickable {
            self.near_since = None;
            (distance <= 0.0, distance <= LEAVE_TOLERANCE)
        } else {
            let near = distance <= reveal.distance && !sample.button_down;
            if near {
                let since = *self.near_since.get_or_insert(sample.now);
                let dwelt = sample.now.saturating_duration_since(since) >= reveal.delay;
                // Stay revealed until the UI's open shape takes over.
                (false, self.inside || dwelt)
            } else {
                self.near_since = None;
                (false, false)
            }
        };
        let pointer = (inside != self.inside).then_some(inside);
        self.inside = inside;
        Decision {
            interactive,
            pointer,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn at(start: Instant, ms: u64) -> Instant {
        start + Duration::from_millis(ms)
    }

    fn idle(distance: f64, button_down: bool, now: Instant) -> Sample {
        Sample {
            distance: Some(distance),
            clickable: false,
            button_down,
            now,
        }
    }

    fn open(distance: f64, now: Instant) -> Sample {
        Sample {
            distance: Some(distance),
            clickable: true,
            button_down: false,
            now,
        }
    }

    #[test]
    fn idle_drop_never_takes_clicks() {
        let t0 = Instant::now();
        let mut tracker = Tracker::default();
        for ms in [0, 50, 200, 1000] {
            assert!(
                !tracker
                    .update(idle(0.0, false, at(t0, ms)), Reveal::default())
                    .interactive
            );
        }
    }

    #[test]
    fn reveals_only_after_dwelling_near() {
        let t0 = Instant::now();
        let reveal = Reveal::default();
        let mut tracker = Tracker::default();
        assert_eq!(
            tracker.update(idle(4.0, false, at(t0, 0)), reveal).pointer,
            None
        );
        assert_eq!(
            tracker
                .update(idle(4.0, false, at(t0, 100)), reveal)
                .pointer,
            None
        );
        assert_eq!(
            tracker
                .update(idle(4.0, false, at(t0, 150)), reveal)
                .pointer,
            Some(true)
        );
        assert_eq!(
            tracker
                .update(idle(4.0, false, at(t0, 200)), reveal)
                .pointer,
            None
        );
    }

    #[test]
    fn passing_by_does_not_reveal() {
        let t0 = Instant::now();
        let reveal = Reveal::default();
        let mut tracker = Tracker::default();
        tracker.update(idle(2.0, false, at(t0, 0)), reveal);
        tracker.update(idle(30.0, false, at(t0, 100)), reveal); // moved away: timer resets
        assert_eq!(
            tracker
                .update(idle(2.0, false, at(t0, 160)), reveal)
                .pointer,
            None
        );
        assert_eq!(
            tracker
                .update(idle(2.0, false, at(t0, 310)), reveal)
                .pointer,
            Some(true)
        );
    }

    #[test]
    fn too_far_never_reveals() {
        let t0 = Instant::now();
        let mut tracker = Tracker::default();
        for ms in [0, 500, 2000] {
            let d = tracker.update(idle(6.5, false, at(t0, ms)), Reveal::default());
            assert_eq!(d.pointer, None);
        }
    }

    #[test]
    fn held_button_blocks_reveal() {
        let t0 = Instant::now();
        let mut tracker = Tracker::default();
        for ms in [0, 200, 400] {
            let d = tracker.update(idle(0.0, true, at(t0, ms)), Reveal::default());
            assert_eq!(d.pointer, None);
        }
    }

    #[test]
    fn open_shape_takes_clicks_inside_only_and_closes_past_tolerance() {
        let t0 = Instant::now();
        let reveal = Reveal::default();
        let mut tracker = Tracker::default();
        tracker.update(idle(0.0, false, at(t0, 0)), reveal);
        tracker.update(idle(0.0, false, at(t0, 150)), reveal); // revealed
        let d = tracker.update(open(0.0, at(t0, 170)), reveal);
        assert_eq!(
            d,
            Decision {
                interactive: true,
                pointer: None
            }
        );
        let d = tracker.update(open(5.0, at(t0, 190)), reveal);
        assert_eq!(
            d,
            Decision {
                interactive: false,
                pointer: None
            }
        );
        let d = tracker.update(open(8.5, at(t0, 210)), reveal);
        assert_eq!(
            d,
            Decision {
                interactive: false,
                pointer: Some(false)
            }
        );
    }

    #[test]
    fn zero_delay_and_distance_reveal_on_touch() {
        let reveal = Reveal {
            distance: 0.0,
            delay: Duration::ZERO,
        };
        let t0 = Instant::now();
        let mut tracker = Tracker::default();
        assert_eq!(tracker.update(idle(0.5, false, t0), reveal).pointer, None);
        assert_eq!(
            tracker.update(idle(0.0, false, t0), reveal).pointer,
            Some(true)
        );
    }

    #[test]
    fn unknown_distance_is_far() {
        let mut tracker = Tracker::default();
        let sample = Sample {
            distance: None,
            clickable: true,
            button_down: false,
            now: Instant::now(),
        };
        assert!(!tracker.update(sample, Reveal::default()).interactive);
    }
}
