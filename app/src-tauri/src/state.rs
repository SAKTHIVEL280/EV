//! Shared app state managed by Tauri.

use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};

use tokio::sync::watch;

use crate::core::CoreStatus;

#[derive(Debug)]
pub struct AppState {
    core_status: Mutex<CoreStatus>,
    pub shutdown: watch::Sender<bool>,
    pub supervisor: Mutex<Option<tauri::async_runtime::JoinHandle<()>>>,
    painted: AtomicBool,
}

impl AppState {
    #[must_use]
    pub fn new(shutdown: watch::Sender<bool>) -> Self {
        Self {
            core_status: Mutex::new(CoreStatus::Starting),
            shutdown,
            supervisor: Mutex::new(None),
            painted: AtomicBool::new(false),
        }
    }

    #[must_use]
    pub fn core_status(&self) -> CoreStatus {
        self.core_status
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone()
    }

    /// True only on the first call.
    pub fn mark_painted(&self) -> bool {
        !self.painted.swap(true, Ordering::Relaxed)
    }

    pub fn set_core_status(&self, status: CoreStatus) {
        *self
            .core_status
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = status;
    }
}
