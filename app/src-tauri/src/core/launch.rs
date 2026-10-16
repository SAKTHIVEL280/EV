//! How to start core.
//!
//! - Release: the `PyInstaller` onedir build shipped as a bundle resource,
//!   `<resources>/ev-core/ev-core(.exe)` (docs/ARCHITECTURE.md §5.2), with
//!   llama.cpp in `<resources>/llama/`.
//! - Debug: the developer's `core/.venv` interpreter running `-m ev_core`
//!   (run `uv sync` in `core/` first), with llama.cpp from
//!   `vendor/llama.cpp/<platform>/` (`scripts/fetch-llama-cpp`).

use std::ffi::OsString;
use std::path::{Path, PathBuf};

use crate::error::AppError;

#[derive(Debug, Clone)]
pub struct LaunchSpec {
    pub program: PathBuf,
    pub args: Vec<OsString>,
    pub data_dir: PathBuf,
    /// Folder with llama-server, passed to core as `EV_LLAMA_DIR`.
    pub llama_dir: Option<PathBuf>,
}

/// Pinned llama.cpp build used in development (`scripts/llama-cpp.pins`).
const DEV_LLAMA_VARIANT: &str = if cfg!(windows) {
    "win-cpu-x64"
} else {
    "ubuntu-x64"
};

const EXE: &str = if cfg!(windows) {
    "ev-core.exe"
} else {
    "ev-core"
};

/// # Errors
/// When the executable does not exist.
pub fn packaged(resource_dir: &Path, data_dir: PathBuf) -> Result<LaunchSpec, AppError> {
    let spec = existing(resource_dir.join("ev-core").join(EXE), Vec::new(), data_dir)?;
    Ok(LaunchSpec {
        llama_dir: Some(resource_dir.join("llama")),
        ..spec
    })
}

/// # Errors
/// When `core/.venv` has not been created with `uv sync`.
pub fn development(core_dir: &Path, data_dir: PathBuf) -> Result<LaunchSpec, AppError> {
    let python = if cfg!(windows) {
        core_dir.join(".venv").join("Scripts").join("python.exe")
    } else {
        core_dir.join(".venv").join("bin").join("python")
    };
    let spec = existing(python, vec!["-m".into(), "ev_core".into()], data_dir)?;
    let llama = core_dir
        .join("..")
        .join("vendor")
        .join("llama.cpp")
        .join(DEV_LLAMA_VARIANT);
    Ok(LaunchSpec {
        llama_dir: llama.is_dir().then_some(llama),
        ..spec
    })
}

fn existing(
    program: PathBuf,
    args: Vec<OsString>,
    data_dir: PathBuf,
) -> Result<LaunchSpec, AppError> {
    if program.is_file() {
        Ok(LaunchSpec {
            program,
            args,
            data_dir,
            llama_dir: None,
        })
    } else {
        Err(AppError::CoreMissing(program.display().to_string()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_executables_are_reported() {
        let dir = tempfile::tempdir().unwrap();
        assert!(matches!(
            packaged(dir.path(), dir.path().into()),
            Err(AppError::CoreMissing(_))
        ));
        assert!(matches!(
            development(dir.path(), dir.path().into()),
            Err(AppError::CoreMissing(_))
        ));
    }

    #[test]
    fn packaged_path_layout() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("ev-core")).unwrap();
        std::fs::write(dir.path().join("ev-core").join(EXE), b"").unwrap();
        let spec = packaged(dir.path(), dir.path().join("data")).unwrap();
        assert_eq!(spec.program, dir.path().join("ev-core").join(EXE));
        assert_eq!(spec.args.len(), 0);
    }
}
