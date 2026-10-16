//! Shared app state managed by Tauri.

use std::sync::Mutex;

use tokio::sync::watch;

use crate::core::CoreStatus;

#[derive(Debug)]
pub struct AppState {
    core_status: Mutex<CoreStatus>,
    pub shutdown: watch::Sender<bool>,
    pub supervisor: Mutex<Option<tauri::async_runtime::JoinHandle<()>>>,
}

impl AppState {
    #[must_use]
    pub fn new(shutdown: watch::Sender<bool>) -> Self {
        Self {
            core_status: Mutex::new(CoreStatus::Starting),
            shutdown,
            supervisor: Mutex::new(None),
        }
    }

    #[must_use]
    pub fn core_status(&self) -> CoreStatus {
        self.core_status
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone()
    }

    pub fn set_core_status(&self, status: CoreStatus) {
        *self
            .core_status
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = status;
    }
}
