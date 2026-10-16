//! Typed errors: a short user-facing message plus technical detail for the log.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("data directory unavailable: {0}")]
    DataDir(String),
    #[error("i/o error: {0}")]
    Io(#[from] std::io::Error),
    #[error("core executable not found at {0}")]
    CoreMissing(String),
    #[error("core protocol mismatch: {0}")]
    ProtocolMismatch(String),
    #[error("core rejected its environment (exit code 2)")]
    CoreBadEnv,
    #[error("random number generator failed: {0}")]
    Random(String),
}

impl AppError {
    /// Short, plain text for the island. Never contains technical detail.
    #[must_use]
    pub fn user_message(&self) -> &'static str {
        match self {
            Self::DataDir(_) | Self::Io(_) => "EV can't use its data folder.",
            Self::CoreMissing(_) | Self::ProtocolMismatch(_) | Self::CoreBadEnv => {
                "EV needs to be reinstalled. Its parts are out of sync."
            }
            Self::Random(_) => "EV couldn't start securely.",
        }
    }
}
