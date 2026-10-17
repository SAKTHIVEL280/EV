//! One core process lifetime (docs/ARCHITECTURE.md §2): spawn with a fresh
//! token, read the `listening` line, connect, `hello` / `hello.ack`, then ping
//! every few seconds until shutdown, crash, or silence.

use std::process::Stdio;
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use tokio::io::{AsyncBufReadExt, AsyncRead, BufReader, Lines};
use tokio::net::TcpStream;
use tokio::process::{Child, ChildStdout, Command};
use tokio::sync::watch;
use tokio::time::{MissedTickBehavior, interval, timeout};
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::http::HeaderValue;
use tokio_tungstenite::tungstenite::http::header::AUTHORIZATION;
use tokio_tungstenite::tungstenite::{self, Message as Frame};
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream};

use crate::core::launch::LaunchSpec;
use crate::core::link::CoreLink;
use crate::error::AppError;
use crate::protocol::generated::{HelloAckMessage, ShutdownPayloadReason};
use crate::protocol::{self, Direction, Message, PROTOCOL_VERSION};
use crate::secrets::session_token;

/// Core rejected its environment (bad token format); restarting cannot help.
const EXIT_BAD_ENV: i32 = 2;
const MAX_MISSED_PONGS: u32 = 3;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

type Socket = WebSocketStream<MaybeTlsStream<TcpStream>>;

#[derive(Debug, Clone)]
pub struct Timing {
    pub listen: Duration,
    pub handshake: Duration,
    pub ping_interval: Duration,
    pub shutdown_grace: Duration,
}

impl Default for Timing {
    fn default() -> Self {
        Self {
            listen: Duration::from_secs(10),
            handshake: Duration::from_secs(5),
            ping_interval: Duration::from_secs(5),
            shutdown_grace: Duration::from_secs(3),
        }
    }
}

#[derive(Debug)]
pub enum SessionEnd {
    /// The app asked core to stop and it did.
    Shutdown,
    /// Core died, hung or misbehaved; the restart policy decides what next.
    Crashed(String),
    /// Restarting cannot help (protocol mismatch, bad environment).
    Fatal(AppError),
}

#[derive(Deserialize)]
struct Listening {
    event: String,
    port: u16,
    protocol: u64,
}

/// What a session reports back: the handshake once, then every chat or model
/// message core sends.
pub struct Hooks<'a, F: FnOnce(HelloAckMessage)> {
    pub on_ready: F,
    pub on_message: &'a (dyn Fn(Message) + Sync),
    pub link: &'a CoreLink,
}

impl<F: FnOnce(HelloAckMessage)> std::fmt::Debug for Hooks<'_, F> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Hooks")
            .field("link", &self.link)
            .finish_non_exhaustive()
    }
}

/// Run one core process until it ends.
pub async fn run<F: FnOnce(HelloAckMessage)>(
    spec: &LaunchSpec,
    app_version: &str,
    timing: &Timing,
    hooks: Hooks<'_, F>,
    shutdown: &mut watch::Receiver<bool>,
) -> SessionEnd {
    if *shutdown.borrow() {
        return SessionEnd::Shutdown;
    }
    let token = match session_token() {
        Ok(token) => token,
        Err(e) => return SessionEnd::Fatal(e),
    };

    let mut command = Command::new(&spec.program);
    command
        .args(&spec.args)
        .env("EV_CORE_TOKEN", &token)
        .env("EV_DATA_DIR", &spec.data_dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    if let Some(llama_dir) = &spec.llama_dir {
        command.env("EV_LLAMA_DIR", llama_dir);
    }
    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(e) => return SessionEnd::Crashed(format!("spawn failed: {e}")),
    };
    // Held for the whole session: when this app exits for any reason the pipe
    // closes and core sees EOF on stdin and exits (no orphaned core).
    let stdin = child.stdin.take();
    let (Some(stdout), Some(stderr)) = (child.stdout.take(), child.stderr.take()) else {
        return SessionEnd::Crashed("child pipes unavailable".into());
    };
    tokio::spawn(forward_lines(BufReader::new(stderr).lines(), "core stderr"));

    let link = hooks.link;
    let end = drive(
        &mut child,
        BufReader::new(stdout).lines(),
        &token,
        app_version,
        timing,
        hooks,
        shutdown,
    )
    .await;

    link.detach();
    drop(stdin);
    if matches!(end, SessionEnd::Shutdown)
        && matches!(
            timeout(timing.shutdown_grace, child.wait()).await,
            Ok(Ok(_))
        )
    {
        return end;
    }
    if let Err(e) = child.kill().await {
        tracing::debug!(error = %e, "kill after session end");
    }
    end
}

async fn drive(
    child: &mut Child,
    mut stdout: Lines<BufReader<ChildStdout>>,
    token: &str,
    app_version: &str,
    timing: &Timing,
    hooks: Hooks<'_, impl FnOnce(HelloAckMessage)>,
    shutdown: &mut watch::Receiver<bool>,
) -> SessionEnd {
    let first_line = match timeout(timing.listen, stdout.next_line()).await {
        Err(_) => return SessionEnd::Crashed("no listening line in time".into()),
        Ok(Err(e)) => return SessionEnd::Crashed(format!("reading stdout: {e}")),
        Ok(Ok(Some(text))) => text,
        Ok(Ok(None)) => {
            return match child.wait().await {
                Ok(status) if status.code() == Some(EXIT_BAD_ENV) => {
                    SessionEnd::Fatal(AppError::CoreBadEnv)
                }
                Ok(status) => SessionEnd::Crashed(format!("exited before listening: {status}")),
                Err(e) => SessionEnd::Crashed(format!("exited before listening: {e}")),
            };
        }
    };
    let listening: Listening = match serde_json::from_str(&first_line) {
        Ok(l) => l,
        Err(e) => return SessionEnd::Crashed(format!("bad listening line: {e}")),
    };
    if listening.event != "listening" {
        return SessionEnd::Crashed(format!("unexpected first line event {:?}", listening.event));
    }
    if listening.protocol != PROTOCOL_VERSION {
        return SessionEnd::Fatal(AppError::ProtocolMismatch(format!(
            "core protocol {}, app protocol {PROTOCOL_VERSION}",
            listening.protocol
        )));
    }
    tokio::spawn(forward_lines(stdout, "unexpected core stdout"));

    let mut ws = match connect(listening.port, token, timing.handshake).await {
        Ok(ws) => ws,
        Err(reason) => return SessionEnd::Crashed(reason),
    };
    let ack = match handshake(&mut ws, app_version, timing.handshake).await {
        Ok(ack) => ack,
        Err(end) => return end,
    };
    // Attach before reporting ready: observers may send right away.
    let mut outbound = hooks.link.attach();
    (hooks.on_ready)(ack);

    let mut ticker = interval(timing.ping_interval);
    ticker.set_missed_tick_behavior(MissedTickBehavior::Delay);
    ticker.tick().await;
    let mut outstanding = 0_u32;
    loop {
        tokio::select! {
            _ = ticker.tick() => {
                if outstanding >= MAX_MISSED_PONGS {
                    return SessionEnd::Crashed(format!("no pong for {outstanding} pings"));
                }
                if let Err(reason) = send(&mut ws, protocol::ping()).await {
                    return SessionEnd::Crashed(reason);
                }
                outstanding += 1;
            }
            frame = ws.next() => match frame {
                None | Some(Err(_) | Ok(Frame::Close(_))) => {
                    return SessionEnd::Crashed("connection closed".into());
                }
                Some(Ok(Frame::Text(text))) => match protocol::decode(text.as_str()) {
                    Ok(Message::Pong(_)) => outstanding = 0,
                    Ok(Message::Error(e)) => {
                        tracing::warn!(code = %*e.payload.code, "core reported error");
                    }
                    Ok(m) if m.direction() == Direction::FromCore => (hooks.on_message)(m),
                    Ok(m) => tracing::warn!(kind = m.kind(), "unexpected message from core"),
                    Err(e) => tracing::warn!(error = %e, "undecodable message from core"),
                },
                Some(Ok(_)) => {}
            },
            Some(message) = outbound.recv() => {
                if let Err(reason) = send(&mut ws, Ok(message)).await {
                    return SessionEnd::Crashed(reason);
                }
            }
            status = child.wait() => {
                return SessionEnd::Crashed(match status {
                    Ok(status) => format!("exited: {status}"),
                    Err(e) => format!("wait failed: {e}"),
                });
            }
            _ = shutdown.changed() => {
                if let Err(reason) = send(&mut ws, protocol::shutdown(ShutdownPayloadReason::AppExit)).await {
                    tracing::debug!(%reason, "shutdown message not delivered");
                }
                return SessionEnd::Shutdown;
            }
        }
    }
}

async fn connect(port: u16, token: &str, limit: Duration) -> Result<Socket, String> {
    let mut request = format!("ws://127.0.0.1:{port}/")
        .into_client_request()
        .map_err(|e| e.to_string())?;
    let auth = HeaderValue::from_str(&format!("Bearer {token}")).map_err(|e| e.to_string())?;
    request.headers_mut().insert(AUTHORIZATION, auth);
    match timeout(limit, tokio_tungstenite::connect_async(request)).await {
        Err(_) => Err("connect timed out".into()),
        Ok(Err(e)) => Err(format!("connect failed: {e}")),
        Ok(Ok((ws, _response))) => Ok(ws),
    }
}

async fn handshake(
    ws: &mut Socket,
    app_version: &str,
    limit: Duration,
) -> Result<HelloAckMessage, SessionEnd> {
    send(ws, protocol::hello(app_version))
        .await
        .map_err(SessionEnd::Crashed)?;
    let reply = timeout(limit, async {
        loop {
            match ws.next().await {
                Some(Ok(Frame::Text(text))) => {
                    return protocol::decode(text.as_str()).map_err(|e| e.to_string());
                }
                Some(Ok(_)) => {}
                Some(Err(e)) => return Err(e.to_string()),
                None => return Err("closed during handshake".into()),
            }
        }
    })
    .await;
    match reply {
        Err(_) => Err(SessionEnd::Crashed("no hello.ack in time".into())),
        Ok(Err(reason)) => Err(SessionEnd::Crashed(reason)),
        Ok(Ok(Message::HelloAck(ack))) => Ok(ack),
        Ok(Ok(Message::Error(e))) if *e.payload.code == "protocol_mismatch" => {
            Err(SessionEnd::Fatal(AppError::ProtocolMismatch(
                e.payload.detail.map(String::from).unwrap_or_default(),
            )))
        }
        Ok(Ok(_)) => Err(SessionEnd::Crashed("unexpected reply to hello".into())),
    }
}

async fn send(ws: &mut Socket, message: Result<Message, AppError>) -> Result<(), String> {
    let message = message.map_err(|e| e.to_string())?;
    let text = protocol::encode(&message).map_err(|e| e.to_string())?;
    ws.send(Frame::text(text))
        .await
        .map_err(|e: tungstenite::Error| e.to_string())
}

async fn forward_lines<R: AsyncRead + Unpin>(mut lines: Lines<BufReader<R>>, what: &'static str) {
    loop {
        match lines.next_line().await {
            Ok(Some(line)) => tracing::warn!(target: "core", line = %line, "{what}"),
            Ok(None) => return,
            Err(e) => {
                tracing::debug!(error = %e, "{what} closed");
                return;
            }
        }
    }
}
