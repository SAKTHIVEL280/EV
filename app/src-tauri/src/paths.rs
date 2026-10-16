//! Data directory resolution. Mirrors `ev_core.paths` (docs/ARCHITECTURE.md §4.4);
//! the app passes the result to core as `EV_DATA_DIR`, so both always agree.

use std::path::PathBuf;

use crate::error::AppError;

pub const APP_DIR_NAME: &str = "EV";

/// `lookup` reads an environment variable (injected for tests).
///
/// # Errors
/// On Windows when `APPDATA` is unset; elsewhere when no home directory is known.
pub fn data_dir(
    lookup: impl Fn(&str) -> Option<String>,
    windows: bool,
) -> Result<PathBuf, AppError> {
    if let Some(dir) = lookup("EV_DATA_DIR").filter(|v| !v.is_empty()) {
        return Ok(PathBuf::from(dir));
    }
    if windows {
        return lookup("APPDATA")
            .filter(|v| !v.is_empty())
            .map(|appdata| PathBuf::from(appdata).join(APP_DIR_NAME))
            .ok_or_else(|| AppError::DataDir("APPDATA is not set".into()));
    }
    if let Some(xdg) = lookup("XDG_DATA_HOME")
        .map(PathBuf::from)
        .filter(|p| p.is_absolute())
    {
        return Ok(xdg.join(APP_DIR_NAME));
    }
    lookup("HOME")
        .filter(|v| !v.is_empty())
        .map(|home| {
            PathBuf::from(home)
                .join(".local")
                .join("share")
                .join(APP_DIR_NAME)
        })
        .ok_or_else(|| AppError::DataDir("HOME is not set".into()))
}

/// Data directory for the current process environment and OS.
///
/// # Errors
/// See [`data_dir`].
pub fn current_data_dir() -> Result<PathBuf, AppError> {
    data_dir(|key| std::env::var(key).ok(), cfg!(windows))
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::path::Path;

    use super::*;

    fn env(pairs: &[(&str, &str)]) -> impl Fn(&str) -> Option<String> {
        let map: HashMap<String, String> = pairs
            .iter()
            .map(|(k, v)| ((*k).to_owned(), (*v).to_owned()))
            .collect();
        move |key| map.get(key).cloned()
    }

    #[test]
    fn override_wins() {
        let lookup = env(&[("EV_DATA_DIR", "/custom"), ("APPDATA", "C:/x")]);
        assert_eq!(data_dir(&lookup, true).unwrap(), Path::new("/custom"));
        assert_eq!(data_dir(&lookup, false).unwrap(), Path::new("/custom"));
    }

    #[test]
    fn windows_uses_appdata() {
        let dir = data_dir(env(&[("APPDATA", "C:/Roaming")]), true).unwrap();
        assert_eq!(dir, Path::new("C:/Roaming").join("EV"));
        assert!(data_dir(env(&[]), true).is_err());
    }

    #[test]
    fn linux_xdg_then_home() {
        assert_eq!(
            data_dir(env(&[("XDG_DATA_HOME", "/xdg")]), false).unwrap(),
            Path::new("/xdg/EV")
        );
        assert_eq!(
            data_dir(env(&[("XDG_DATA_HOME", "rel"), ("HOME", "/home/u")]), false).unwrap(),
            Path::new("/home/u/.local/share/EV")
        );
        assert!(data_dir(env(&[]), false).is_err());
    }
}
