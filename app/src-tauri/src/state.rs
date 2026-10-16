//! Shared app state managed by Tauri.

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use tokio::sync::watch;

use crate::chat::LlmStatus;
use crate::core::CoreStatus;
use crate::core::link::CoreLink;
use crate::settings::SettingsState;

#[derive(Debug)]
pub struct AppState {
    core_status: Mutex<CoreStatus>,
    llm_status: Mutex<LlmStatus>,
    pub link: Arc<CoreLink>,
    settings: Mutex<Option<SettingsState>>,
    pub data_dir: PathBuf,
    pub shutdown: watch::Sender<bool>,
    pub supervisor: Mutex<Option<tauri::async_runtime::JoinHandle<()>>>,
    painted: AtomicBool,
}

impl AppState {
    #[must_use]
    pub fn new(shutdown: watch::Sender<bool>, data_dir: PathBuf) -> Self {
        Self {
            core_status: Mutex::new(CoreStatus::Starting),
            llm_status: Mutex::new(LlmStatus::unloaded()),
            link: Arc::new(CoreLink::default()),
            settings: Mutex::new(None),
            data_dir,
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

    #[must_use]
    pub fn llm_status(&self) -> LlmStatus {
        self.llm_status
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone()
    }

    pub fn set_llm_status(&self, status: LlmStatus) {
        *self
            .llm_status
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = status;
    }

    #[must_use]
    pub fn settings(&self) -> Option<SettingsState> {
        self.settings
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .clone()
    }

    pub fn set_settings(&self, state: SettingsState) {
        *self
            .settings
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(state);
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
