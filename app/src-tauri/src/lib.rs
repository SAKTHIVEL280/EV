//! EV desktop app: island window and supervisor of `ev-core`
//! (docs/ARCHITECTURE.md §5).

pub mod chat;
pub mod commands;
pub mod core;
pub mod error;
pub mod island;
pub mod logging;
pub mod paths;
pub mod platform;
pub mod protocol;
pub mod secrets;
pub mod settings;
pub mod settings_window;
pub mod state;

use std::path::PathBuf;
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent, Runtime};
use tauri_specta::{Event, collect_commands, collect_events};
use tokio::sync::watch;
use tracing_subscriber::filter::LevelFilter;

use crate::chat::{ChatUpdate, LlmStatus, LlmStatusChanged, Update};
use crate::core::launch::{self, LaunchSpec};
use crate::core::policy::RestartPolicy;
use crate::core::session::Timing;
use crate::core::{CoreObserver, CoreStatus, CoreStatusChanged, supervise};
use crate::error::AppError;
use crate::island::{IslandPointer, IslandState, IslandVisibility};
use crate::protocol::Message;
use crate::state::AppState;

pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");
const SHUTDOWN_WAIT: Duration = Duration::from_secs(5);

static STARTED: OnceLock<Instant> = OnceLock::new();

/// When `run` began (first call wins); the reference for startup timings.
pub fn started_at() -> Instant {
    *STARTED.get_or_init(Instant::now)
}

/// Commands and events exposed to the UI. Also used to generate
/// `app/src/lib/bindings.ts`.
#[must_use]
pub fn specta_builder<R: Runtime>() -> tauri_specta::Builder<R> {
    tauri_specta::Builder::<R>::new()
        .commands(collect_commands![
            commands::island_set_hit_rect,
            commands::island_set_panel_open::<tauri::Wry>,
            commands::core_status,
            commands::app_quit::<tauri::Wry>,
            commands::spike_report_frames,
            commands::spike_island_painted,
            commands::chat_send,
            commands::chat_cancel,
            commands::llm_status,
            commands::settings_refresh,
            commands::settings_set,
            commands::settings_reset,
            commands::settings_state,
            commands::settings_open::<tauri::Wry>,
            commands::open_config_file::<tauri::Wry>,
            commands::open_logs_folder::<tauri::Wry>,
        ])
        .events(collect_events![
            CoreStatusChanged,
            IslandPointer,
            IslandVisibility,
            ChatUpdate,
            LlmStatusChanged,
            settings::SettingsChanged,
            settings::SettingRejected
        ])
}

/// Application entry point.
///
/// # Errors
/// When the data directory, logging or the Tauri runtime cannot be set up.
pub fn run() -> Result<(), AppError> {
    started_at();
    let data_dir = paths::current_data_dir()?;
    let level = if cfg!(debug_assertions) {
        LevelFilter::DEBUG
    } else {
        LevelFilter::INFO
    };
    logging::init(&data_dir.join("logs"), level)?;
    tracing::info!(version = APP_VERSION, "app starting");

    let builder = specta_builder::<tauri::Wry>();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(builder.invoke_handler())
        .setup(move |app| {
            builder.mount_events(app);
            let (shutdown_tx, shutdown_rx) = watch::channel(false);
            app.manage(AppState::new(shutdown_tx, data_dir.clone()));
            app.manage(IslandState::default());
            island::create(app.handle())?;
            start_supervisor(app.handle(), data_dir.clone(), shutdown_rx);
            Ok(())
        })
        .build(tauri::generate_context!())
        .map_err(|e| AppError::Io(std::io::Error::other(e.to_string())))?;

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_supervisor(handle);
        }
    });
    Ok(())
}

fn launch_spec<R: Runtime>(app: &AppHandle<R>, data_dir: PathBuf) -> Result<LaunchSpec, AppError> {
    if cfg!(debug_assertions) {
        let core_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("core");
        launch::development(&core_dir, data_dir)
    } else {
        let resources = app
            .path()
            .resource_dir()
            .map_err(|e| AppError::CoreMissing(e.to_string()))?;
        launch::packaged(&resources, data_dir)
    }
}

/// Forwards core state to app state and UI events.
struct AppObserver<R: Runtime> {
    app: AppHandle<R>,
}

impl<R: Runtime> AppObserver<R> {
    fn settings_message(&self, message: Message) {
        match settings::update(message) {
            Some(settings::Update::State(state)) => {
                self.app.state::<AppState>().set_settings(state.clone());
                if let Err(e) = settings::SettingsChanged(state).emit(&self.app) {
                    tracing::warn!(error = %e, "emit SettingsChanged failed");
                }
            }
            Some(settings::Update::Rejected(rejected)) => {
                if let Err(e) = rejected.emit(&self.app) {
                    tracing::warn!(error = %e, "emit SettingRejected failed");
                }
            }
            None => {}
        }
    }

    fn set_llm(&self, status: LlmStatus) {
        self.app.state::<AppState>().set_llm_status(status.clone());
        if let Err(e) = LlmStatusChanged(status).emit(&self.app) {
            tracing::warn!(error = %e, "emit LlmStatusChanged failed");
        }
    }
}

impl<R: Runtime> CoreObserver for AppObserver<R> {
    fn status(&self, status: CoreStatus) {
        // A core that is not running has no model loaded.
        if !matches!(status, CoreStatus::Running { .. }) {
            self.set_llm(LlmStatus::unloaded());
        }
        self.app.state::<AppState>().set_core_status(status.clone());
        if let Err(e) = CoreStatusChanged(status).emit(&self.app) {
            tracing::warn!(error = %e, "emit CoreStatusChanged failed");
        }
    }

    fn message(&self, message: Message) {
        if matches!(
            message,
            Message::ConfigState(_) | Message::ConfigRejected(_)
        ) {
            self.settings_message(message);
            return;
        }
        match chat::update(message) {
            Some(Update::Chat(update)) => {
                if let Err(e) = ChatUpdate(update).emit(&self.app) {
                    tracing::warn!(error = %e, "emit ChatUpdate failed");
                }
            }
            Some(Update::Llm(status)) => self.set_llm(status),
            None => {}
        }
    }
}

fn start_supervisor<R: Runtime>(
    app: &AppHandle<R>,
    data_dir: PathBuf,
    shutdown: watch::Receiver<bool>,
) {
    let spec = launch_spec(app, data_dir);
    let observer = AppObserver { app: app.clone() };
    let link = app.state::<AppState>().link.clone();
    let handle = tauri::async_runtime::spawn(async move {
        supervise(
            spec,
            APP_VERSION,
            &Timing::default(),
            RestartPolicy::default(),
            shutdown,
            &observer,
            &link,
        )
        .await;
    });
    *app.state::<AppState>()
        .supervisor
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(handle);
}

/// Ask core to stop and wait briefly so it can exit cleanly.
fn stop_supervisor<R: Runtime>(app: &AppHandle<R>) {
    let state = app.state::<AppState>();
    if state.shutdown.send(true).is_err() {
        return;
    }
    let handle = state
        .supervisor
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
        .take();
    if let Some(handle) = handle {
        let finished = tauri::async_runtime::block_on(async {
            tokio::time::timeout(SHUTDOWN_WAIT, handle).await
        });
        if finished.is_err() {
            tracing::warn!("core did not stop in time");
        }
    }
    tracing::info!("app exiting");
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use specta_typescript::Typescript;

    use super::*;

    /// `app/src/lib/bindings.ts` must match the Rust commands and events.
    /// Regenerate with `EV_UPDATE_BINDINGS=1 cargo test bindings` (or scripts/codegen-bindings).
    #[test]
    fn bindings_are_up_to_date() {
        let committed = Path::new(env!("CARGO_MANIFEST_DIR")).join("../src/lib/bindings.ts");
        let builder = specta_builder::<tauri::Wry>();
        let language = Typescript::default().header("// Generated by tauri-specta from app/src-tauri. Do not edit; run scripts/codegen-bindings.\n// @ts-nocheck\n");
        if std::env::var_os("EV_UPDATE_BINDINGS").is_some() {
            builder.export(language, &committed).unwrap();
            return;
        }
        let dir = tempfile::tempdir().unwrap();
        let fresh = dir.path().join("bindings.ts");
        builder.export(language, &fresh).unwrap();
        assert_eq!(
            std::fs::read_to_string(&fresh).unwrap(),
            std::fs::read_to_string(&committed).unwrap_or_default(),
            "app/src/lib/bindings.ts is stale; run scripts/codegen-bindings"
        );
    }
}
