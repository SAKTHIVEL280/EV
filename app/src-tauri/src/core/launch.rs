//! How to start core.
//!
//! - Release: the `PyInstaller` onedir build shipped as a bundle resource,
//!   `<resources>/ev-core/ev-core(.exe)` (docs/ARCHITECTURE.md §5.2).
//! - Debug: the developer's `core/.venv` interpreter running `-m ev_core`
//!   (run `uv sync` in `core/` first).

use std::ffi::OsString;
use std::path::{Path, PathBuf};

use crate::error::AppError;

#[derive(Debug, Clone)]
pub struct LaunchSpec {
    pub program: PathBuf,
    pub args: Vec<OsString>,
    pub data_dir: PathBuf,
}

const EXE: &str = if cfg!(windows) {
    "ev-core.exe"
} else {
    "ev-core"
};

/// # Errors
/// When the executable does not exist.
pub fn packaged(resource_dir: &Path, data_dir: PathBuf) -> Result<LaunchSpec, AppError> {
    existing(resource_dir.join("ev-core").join(EXE), Vec::new(), data_dir)
}

/// # Errors
/// When `core/.venv` has not been created with `uv sync`.
pub fn development(core_dir: &Path, data_dir: PathBuf) -> Result<LaunchSpec, AppError> {
    let python = if cfg!(windows) {
        core_dir.join(".venv").join("Scripts").join("python.exe")
    } else {
        core_dir.join(".venv").join("bin").join("python")
    };
    existing(python, vec!["-m".into(), "ev_core".into()], data_dir)
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
