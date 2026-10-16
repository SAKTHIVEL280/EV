//! Core supervisor: keeps `ev-core` running and reports its status
//! (CLAUDE.md §5.1, docs/ARCHITECTURE.md §1–2).

pub mod launch;
pub mod policy;
pub mod session;
pub mod status;

use std::time::Instant;

use tokio::sync::watch;
use tokio::time::sleep;

use crate::error::AppError;
use crate::protocol::generated::HelloAckMessage;
use launch::LaunchSpec;
use policy::RestartPolicy;
use session::{SessionEnd, Timing};
pub use status::{CoreStatus, CoreStatusChanged, ModuleInfo};

pub const CORE_STOPPED: &str = "EV's core stopped and couldn't restart. Details are in the log.";

/// Run until shutdown is signalled or the restart policy gives up.
/// Every state change is passed to `report`.
pub async fn supervise(
    spec: Result<LaunchSpec, AppError>,
    app_version: &str,
    timing: &Timing,
    mut policy: RestartPolicy,
    mut shutdown: watch::Receiver<bool>,
    report: impl Fn(CoreStatus),
) {
    let spec = match spec {
        Ok(spec) => spec,
        Err(e) => {
            tracing::error!(error = %e, "core cannot be launched");
            report(CoreStatus::Failed {
                message: e.user_message().into(),
            });
            return;
        }
    };
    loop {
        if *shutdown.borrow() {
            return;
        }
        report(CoreStatus::Starting);
        let started = Instant::now();
        let end = session::run(
            &spec,
            app_version,
            timing,
            |ack| report(running(&ack)),
            &mut shutdown,
        )
        .await;
        match end {
            SessionEnd::Shutdown => {
                tracing::info!("core stopped on request");
                return;
            }
            SessionEnd::Fatal(e) => {
                tracing::error!(error = %e, "core failed permanently");
                report(CoreStatus::Failed {
                    message: e.user_message().into(),
                });
                return;
            }
            SessionEnd::Crashed(reason) => {
                tracing::warn!(%reason, uptime_ms = u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX), "core crashed");
                let Some((attempt, delay)) = policy.on_crash(started.elapsed()) else {
                    tracing::error!("core restart policy exhausted");
                    report(CoreStatus::Failed {
                        message: CORE_STOPPED.into(),
                    });
                    return;
                };
                report(CoreStatus::Restarting {
                    attempt,
                    delay_ms: u32::try_from(delay.as_millis()).unwrap_or(u32::MAX),
                });
                tokio::select! {
                    () = sleep(delay) => {}
                    _ = shutdown.changed() => return,
                }
            }
        }
    }
}

fn running(ack: &HelloAckMessage) -> CoreStatus {
    tracing::info!(core_version = %*ack.payload.core_version, "core ready");
    CoreStatus::Running {
        core_version: ack.payload.core_version.as_str().to_owned(),
        modules: ack
            .payload
            .modules
            .iter()
            .map(|m| ModuleInfo {
                name: m.name.as_str().to_owned(),
                state: m.state.to_string(),
                detail: m.detail.as_ref().map(|d| d.as_str().to_owned()),
            })
            .collect(),
    }
}

#[cfg(test)]
mod tests {
    use std::path::Path;
    use std::sync::{Arc, Mutex};
    use std::time::Duration;

    use super::*;

    fn recorder() -> (Arc<Mutex<Vec<CoreStatus>>>, impl Fn(CoreStatus) + Clone) {
        let log = Arc::new(Mutex::new(Vec::new()));
        let sink = log.clone();
        (log, move |s| sink.lock().unwrap().push(s))
    }

    fn fast_policy() -> RestartPolicy {
        RestartPolicy::new(vec![Duration::from_millis(10); 3], Duration::from_mins(1))
    }

    fn fast_timing() -> Timing {
        Timing {
            listen: Duration::from_secs(10),
            handshake: Duration::from_secs(5),
            ping_interval: Duration::from_millis(200),
            shutdown_grace: Duration::from_secs(5),
        }
    }

    /// The real Python core from `core/.venv` (run `uv sync` in `core/` first).
    fn real_core(data_dir: &Path) -> LaunchSpec {
        let core_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../core");
        launch::development(&core_dir, data_dir.to_path_buf())
            .expect("core/.venv missing: run `uv sync` in core/ before cargo test")
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn real_core_handshakes_pings_and_shuts_down() {
        let dir = tempfile::tempdir().unwrap();
        let (log, report) = recorder();
        let (tx, rx) = watch::channel(false);
        let spec = real_core(dir.path());
        let task = tokio::spawn(async move {
            supervise(
                Ok(spec),
                "0.1.0-beta.1",
                &fast_timing(),
                fast_policy(),
                rx,
                report,
            )
            .await;
        });

        let deadline = Instant::now() + Duration::from_secs(30);
        while !log
            .lock()
            .unwrap()
            .iter()
            .any(|s| matches!(s, CoreStatus::Running { .. }))
        {
            assert!(
                Instant::now() < deadline,
                "core never became ready: {:?}",
                log.lock().unwrap()
            );
            sleep(Duration::from_millis(50)).await;
        }
        // Several ping intervals pass without a crash.
        sleep(Duration::from_millis(1000)).await;
        tx.send(true).unwrap();
        tokio::time::timeout(Duration::from_secs(10), task)
            .await
            .unwrap()
            .unwrap();

        let log = log.lock().unwrap();
        assert_eq!(log[0], CoreStatus::Starting);
        assert!(
            matches!(&log[1], CoreStatus::Running { core_version, .. } if !core_version.is_empty())
        );
        assert_eq!(log.len(), 2, "{log:?}");
        let core_log = std::fs::read_to_string(dir.path().join("logs").join("core.log")).unwrap();
        assert!(
            core_log.contains("\"shutdown requested\""),
            "core did not get the shutdown message"
        );
    }

    #[tokio::test]
    async fn missing_executable_fails_without_retry() {
        let (log, report) = recorder();
        let (_tx, rx) = watch::channel(false);
        supervise(
            Err(AppError::CoreMissing("x".into())),
            "0.1.0",
            &fast_timing(),
            fast_policy(),
            rx,
            report,
        )
        .await;
        assert_eq!(
            *log.lock().unwrap(),
            vec![CoreStatus::Failed {
                message: AppError::CoreMissing(String::new()).user_message().into()
            }]
        );
    }

    #[cfg(unix)]
    fn shell(script: &str, data_dir: &Path) -> LaunchSpec {
        LaunchSpec {
            program: "/bin/sh".into(),
            args: vec!["-c".into(), script.into()],
            data_dir: data_dir.into(),
        }
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn crashing_core_restarts_three_times_then_fails() {
        let dir = tempfile::tempdir().unwrap();
        let (log, report) = recorder();
        let (_tx, rx) = watch::channel(false);
        supervise(
            Ok(shell("exit 1", dir.path())),
            "0.1.0",
            &fast_timing(),
            fast_policy(),
            rx,
            report,
        )
        .await;
        let restarting = |attempt| CoreStatus::Restarting {
            attempt,
            delay_ms: 10,
        };
        assert_eq!(
            *log.lock().unwrap(),
            vec![
                CoreStatus::Starting,
                restarting(1),
                CoreStatus::Starting,
                restarting(2),
                CoreStatus::Starting,
                restarting(3),
                CoreStatus::Starting,
                CoreStatus::Failed {
                    message: CORE_STOPPED.into()
                },
            ]
        );
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn bad_env_exit_code_is_fatal() {
        let dir = tempfile::tempdir().unwrap();
        let (log, report) = recorder();
        let (_tx, rx) = watch::channel(false);
        supervise(
            Ok(shell("exit 2", dir.path())),
            "0.1.0",
            &fast_timing(),
            fast_policy(),
            rx,
            report,
        )
        .await;
        let log = log.lock().unwrap();
        assert_eq!(log.len(), 2);
        assert!(matches!(log[1], CoreStatus::Failed { .. }));
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn protocol_mismatch_in_listening_line_is_fatal() {
        let dir = tempfile::tempdir().unwrap();
        let (log, report) = recorder();
        let (_tx, rx) = watch::channel(false);
        let script = r#"echo '{"event":"listening","port":9,"protocol":99}'; sleep 5"#;
        supervise(
            Ok(shell(script, dir.path())),
            "0.1.0",
            &fast_timing(),
            fast_policy(),
            rx,
            report,
        )
        .await;
        let log = log.lock().unwrap();
        assert_eq!(log.len(), 2);
        assert!(matches!(log[1], CoreStatus::Failed { .. }));
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn unreachable_port_counts_as_crash() {
        let dir = tempfile::tempdir().unwrap();
        let (log, report) = recorder();
        let (_tx, rx) = watch::channel(false);
        // Port 9 (discard) is closed on CI and dev machines; connect is refused.
        let script = r#"echo '{"event":"listening","port":9,"protocol":1}'; sleep 5"#;
        supervise(
            Ok(shell(script, dir.path())),
            "0.1.0",
            &fast_timing(),
            fast_policy(),
            rx,
            report,
        )
        .await;
        let log = log.lock().unwrap();
        assert!(
            matches!(log[1], CoreStatus::Restarting { attempt: 1, .. }),
            "{log:?}"
        );
        assert!(matches!(log.last(), Some(CoreStatus::Failed { .. })));
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn shutdown_during_backoff_stops_immediately() {
        let dir = tempfile::tempdir().unwrap();
        let (log, report) = recorder();
        let (tx, rx) = watch::channel(false);
        let slow = RestartPolicy::new(vec![Duration::from_mins(1)], Duration::from_mins(1));
        let spec = shell("exit 1", dir.path());
        let task = tokio::spawn(async move {
            supervise(Ok(spec), "0.1.0", &fast_timing(), slow, rx, report).await;
        });
        let deadline = Instant::now() + Duration::from_secs(10);
        while !log
            .lock()
            .unwrap()
            .iter()
            .any(|s| matches!(s, CoreStatus::Restarting { .. }))
        {
            assert!(Instant::now() < deadline);
            sleep(Duration::from_millis(10)).await;
        }
        tx.send(true).unwrap();
        tokio::time::timeout(Duration::from_secs(2), task)
            .await
            .unwrap()
            .unwrap();
    }
}
