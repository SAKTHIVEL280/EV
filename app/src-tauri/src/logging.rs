//! Structured, rotating, local-only logs (docs/ARCHITECTURE.md §4.5).
//!
//! `logs/app.log` uses the same record shape and rotation policy as core's
//! `logs/core.log`: one JSON object per line with `ts`, `level`, `logger`,
//! `msg` plus structured fields; 5 MB per file, 5 files kept.

use std::fmt::Debug;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{Map, Value};
use tracing::field::{Field, Visit};
use tracing::{Event, Level, Subscriber};
use tracing_subscriber::Layer;
use tracing_subscriber::filter::LevelFilter;
use tracing_subscriber::layer::{Context, SubscriberExt};

use crate::error::AppError;

pub const LOG_FILE_NAME: &str = "app.log";
pub const MAX_BYTES: u64 = 5 * 1024 * 1024;
/// `app.log` plus 4 rotated files = 5 files kept.
pub const BACKUP_COUNT: u32 = 4;

/// Install the global subscriber. Call once, before anything logs.
///
/// # Errors
/// When the log directory or file cannot be created.
pub fn init(log_dir: &Path, level: LevelFilter) -> Result<(), AppError> {
    fs::create_dir_all(log_dir)?;
    let file = RotatingFile::open(log_dir.join(LOG_FILE_NAME), MAX_BYTES, BACKUP_COUNT)?;
    let subscriber = tracing_subscriber::registry().with(JsonLayer::new(file).with_filter(level));
    tracing::subscriber::set_global_default(subscriber)
        .map_err(|e| AppError::Io(io::Error::other(e.to_string())))?;
    install_panic_hook();
    Ok(())
}

/// Log panics before the process aborts (release builds use `panic = "abort"`).
fn install_panic_hook() {
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        tracing::error!(panic = %info, "panic");
        previous(info);
    }));
}

/// Size-based rotation: `app.log` → `app.log.1` → … → `app.log.<backups>`.
#[derive(Debug)]
pub struct RotatingFile {
    path: PathBuf,
    max_bytes: u64,
    backups: u32,
    file: File,
    written: u64,
}

impl RotatingFile {
    /// # Errors
    /// When the file cannot be opened.
    pub fn open(path: PathBuf, max_bytes: u64, backups: u32) -> io::Result<Self> {
        let file = OpenOptions::new().create(true).append(true).open(&path)?;
        let written = file.metadata()?.len();
        Ok(Self {
            path,
            max_bytes,
            backups,
            file,
            written,
        })
    }

    fn rotate(&mut self) -> io::Result<()> {
        self.file.flush()?;
        for n in (1..self.backups).rev() {
            let from = self.numbered(n);
            if from.exists() {
                fs::rename(&from, self.numbered(n + 1))?;
            }
        }
        if self.backups > 0 {
            fs::rename(&self.path, self.numbered(1))?;
        }
        self.file = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&self.path)?;
        self.written = 0;
        Ok(())
    }

    fn numbered(&self, n: u32) -> PathBuf {
        let mut name = self.path.as_os_str().to_owned();
        name.push(format!(".{n}"));
        PathBuf::from(name)
    }
}

impl Write for RotatingFile {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        let len = buf.len() as u64;
        if self.written > 0 && self.written + len > self.max_bytes {
            self.rotate()?;
        }
        self.file.write_all(buf)?;
        self.written += len;
        Ok(buf.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        self.file.flush()
    }
}

#[derive(Debug)]
pub struct JsonLayer<W> {
    writer: Mutex<W>,
}

impl<W> JsonLayer<W> {
    pub fn new(writer: W) -> Self {
        Self {
            writer: Mutex::new(writer),
        }
    }
}

impl<S, W> Layer<S> for JsonLayer<W>
where
    S: Subscriber,
    W: Write + Send + 'static,
{
    fn on_event(&self, event: &Event<'_>, _ctx: Context<'_, S>) {
        let line = format_event(event, SystemTime::now());
        // A poisoned lock only means another thread panicked mid-write; keep logging.
        let mut writer = self
            .writer
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        // Logging must never take the app down; a failed write is dropped.
        let _ = writer
            .write_all(line.as_bytes())
            .and_then(|()| writer.flush());
    }
}

const BASE_KEYS: [&str; 5] = ["ts", "level", "logger", "msg", "exc"];

fn format_event(event: &Event<'_>, now: SystemTime) -> String {
    let meta = event.metadata();
    let mut visitor = JsonVisitor::default();
    event.record(&mut visitor);

    let mut entry = Map::new();
    entry.insert("ts".into(), Value::String(iso8601_utc(now)));
    entry.insert(
        "level".into(),
        Value::String(level_name(*meta.level()).into()),
    );
    entry.insert("logger".into(), Value::String(meta.target().into()));
    entry.insert(
        "msg".into(),
        Value::String(visitor.message.unwrap_or_default()),
    );
    for (key, value) in visitor.fields {
        if !BASE_KEYS.contains(&key.as_str()) {
            entry.insert(key, value);
        }
    }
    let mut line = Value::Object(entry).to_string();
    line.push('\n');
    line
}

fn level_name(level: Level) -> &'static str {
    match level {
        Level::ERROR => "error",
        Level::WARN => "warning",
        Level::INFO => "info",
        Level::DEBUG => "debug",
        Level::TRACE => "trace",
    }
}

#[derive(Default)]
struct JsonVisitor {
    message: Option<String>,
    fields: Map<String, Value>,
}

impl JsonVisitor {
    fn put(&mut self, field: &Field, value: Value) {
        if field.name() == "message" {
            self.message = Some(match value {
                Value::String(s) => s,
                other => other.to_string(),
            });
        } else {
            self.fields.insert(field.name().to_owned(), value);
        }
    }
}

impl Visit for JsonVisitor {
    fn record_str(&mut self, field: &Field, value: &str) {
        self.put(field, Value::String(value.to_owned()));
    }
    fn record_bool(&mut self, field: &Field, value: bool) {
        self.put(field, Value::Bool(value));
    }
    fn record_i64(&mut self, field: &Field, value: i64) {
        self.put(field, Value::from(value));
    }
    fn record_u64(&mut self, field: &Field, value: u64) {
        self.put(field, Value::from(value));
    }
    fn record_f64(&mut self, field: &Field, value: f64) {
        self.put(field, Value::from(value));
    }
    fn record_debug(&mut self, field: &Field, value: &dyn Debug) {
        self.put(field, Value::String(format!("{value:?}")));
    }
}

/// `YYYY-MM-DDTHH:MM:SS.mmm+00:00`, matching Python's `isoformat(timespec="milliseconds")`.
fn iso8601_utc(time: SystemTime) -> String {
    let since = time.duration_since(UNIX_EPOCH).unwrap_or_default();
    let secs = since.as_secs();
    let days = i64::try_from(secs / 86_400).unwrap_or(0);
    let rem = secs % 86_400;
    let (y, m, d) = civil_from_days(days);
    format!(
        "{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}.{:03}+00:00",
        rem / 3600,
        (rem % 3600) / 60,
        rem % 60,
        since.subsec_millis()
    )
}

/// Days since 1970-01-01 → (year, month, day). Howard Hinnant's algorithm.
fn civil_from_days(days: i64) -> (i64, u32, u32) {
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    // d is in 1..=31 and m in 1..=12 by construction.
    (
        y,
        u32::try_from(m).unwrap_or(1),
        u32::try_from(d).unwrap_or(1),
    )
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;
    use std::time::Duration;

    use tracing_subscriber::layer::SubscriberExt;

    use super::*;

    #[derive(Clone, Default)]
    struct Shared(Arc<Mutex<Vec<u8>>>);

    impl Write for Shared {
        fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(buf);
            Ok(buf.len())
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn timestamps() {
        assert_eq!(iso8601_utc(UNIX_EPOCH), "1970-01-01T00:00:00.000+00:00");
        // 2026-10-17T12:34:56.789Z
        let t = UNIX_EPOCH + Duration::from_secs(1_792_240_496) + Duration::from_millis(789);
        assert_eq!(iso8601_utc(t), "2026-10-17T12:34:56.789+00:00");
        // Leap day: 11,016 days after the epoch.
        let leap = UNIX_EPOCH + Duration::from_hours(24 * 11_016);
        assert_eq!(iso8601_utc(leap), "2000-02-29T00:00:00.000+00:00");
    }

    #[test]
    fn events_are_json_lines_with_core_shape() {
        let sink = Shared::default();
        let subscriber = tracing_subscriber::registry()
            .with(JsonLayer::new(sink.clone()).with_filter(LevelFilter::INFO));
        tracing::subscriber::with_default(subscriber, || {
            tracing::info!(target: "ev::test", port = 5_u64, ok = true, "core listening");
            tracing::debug!("filtered out");
            tracing::warn!(msg = "spoof", "kept message");
        });
        let text = String::from_utf8(sink.0.lock().unwrap().clone()).unwrap();
        let lines: Vec<Value> = text
            .lines()
            .map(|l| serde_json::from_str(l).unwrap())
            .collect();
        assert_eq!(lines.len(), 2);
        assert_eq!(lines[0]["level"], "info");
        assert_eq!(lines[0]["logger"], "ev::test");
        assert_eq!(lines[0]["msg"], "core listening");
        assert_eq!(lines[0]["port"], 5);
        assert_eq!(lines[0]["ok"], true);
        assert_eq!(lines[1]["level"], "warning");
        assert_eq!(lines[1]["msg"], "kept message");
    }

    #[test]
    fn rotates_by_size_and_keeps_backups() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("app.log");
        let mut file = RotatingFile::open(path.clone(), 10, 2).unwrap();
        for chunk in ["aaaaaaaa\n", "bbbbbbbb\n", "cccccccc\n", "dddddddd\n"] {
            file.write_all(chunk.as_bytes()).unwrap();
        }
        file.flush().unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "dddddddd\n");
        assert_eq!(
            fs::read_to_string(dir.path().join("app.log.1")).unwrap(),
            "cccccccc\n"
        );
        assert_eq!(
            fs::read_to_string(dir.path().join("app.log.2")).unwrap(),
            "bbbbbbbb\n"
        );
        assert!(!dir.path().join("app.log.3").exists());
    }

    #[test]
    fn reopen_appends_and_counts_existing_size() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("app.log");
        fs::write(&path, "123456789\n").unwrap();
        let mut file = RotatingFile::open(path.clone(), 12, 1).unwrap();
        file.write_all(b"next\n").unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "next\n");
        assert_eq!(
            fs::read_to_string(dir.path().join("app.log.1")).unwrap(),
            "123456789\n"
        );
    }
}
