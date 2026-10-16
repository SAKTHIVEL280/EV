//! Restart policy: 1 s, 2 s, 5 s, then stop (CLAUDE.md §5.1).
//!
//! A core that stayed healthy for [`HEALTHY_RESET`] before crashing starts a
//! fresh sequence, so one crash a day never accumulates into "stopped".

use std::time::Duration;

pub const DELAYS: [Duration; 3] = [
    Duration::from_secs(1),
    Duration::from_secs(2),
    Duration::from_secs(5),
];
pub const HEALTHY_RESET: Duration = Duration::from_secs(60);

#[derive(Debug, Clone)]
pub struct RestartPolicy {
    delays: Vec<Duration>,
    healthy_reset: Duration,
    attempts: usize,
}

impl Default for RestartPolicy {
    fn default() -> Self {
        Self::new(DELAYS.to_vec(), HEALTHY_RESET)
    }
}

impl RestartPolicy {
    #[must_use]
    pub fn new(delays: Vec<Duration>, healthy_reset: Duration) -> Self {
        Self {
            delays,
            healthy_reset,
            attempts: 0,
        }
    }

    /// Record a crash after `uptime`; returns `(attempt number, delay)` or
    /// `None` when the policy is exhausted.
    pub fn on_crash(&mut self, uptime: Duration) -> Option<(u32, Duration)> {
        if uptime >= self.healthy_reset {
            self.attempts = 0;
        }
        let delay = *self.delays.get(self.attempts)?;
        self.attempts += 1;
        Some((u32::try_from(self.attempts).unwrap_or(u32::MAX), delay))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backoff_then_stop() {
        let mut policy = RestartPolicy::default();
        let quick = Duration::from_millis(100);
        assert_eq!(policy.on_crash(quick), Some((1, Duration::from_secs(1))));
        assert_eq!(policy.on_crash(quick), Some((2, Duration::from_secs(2))));
        assert_eq!(policy.on_crash(quick), Some((3, Duration::from_secs(5))));
        assert_eq!(policy.on_crash(quick), None);
        assert_eq!(policy.on_crash(quick), None);
    }

    #[test]
    fn healthy_run_resets_sequence() {
        let mut policy = RestartPolicy::default();
        policy.on_crash(Duration::ZERO);
        policy.on_crash(Duration::ZERO);
        assert_eq!(
            policy.on_crash(HEALTHY_RESET),
            Some((1, Duration::from_secs(1)))
        );
    }
}
