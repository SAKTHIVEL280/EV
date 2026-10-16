//! Per-session secrets and message ids from the OS random source.

use std::fmt::Write as _;

use crate::error::AppError;

/// 256-bit token as 64 lowercase hex characters (the format core requires).
///
/// # Errors
/// When the OS random source fails.
pub fn session_token() -> Result<String, AppError> {
    let mut bytes = [0_u8; 32];
    getrandom::fill(&mut bytes).map_err(|e| AppError::Random(e.to_string()))?;
    Ok(hex(&bytes))
}

/// Random UUID v4 in canonical lowercase form.
///
/// # Errors
/// When the OS random source fails.
pub fn uuid_v4() -> Result<String, AppError> {
    let mut b = [0_u8; 16];
    getrandom::fill(&mut b).map_err(|e| AppError::Random(e.to_string()))?;
    b[6] = (b[6] & 0x0f) | 0x40; // version 4
    b[8] = (b[8] & 0x3f) | 0x80; // RFC 4122 variant
    let h = hex(&b);
    Ok(format!(
        "{}-{}-{}-{}-{}",
        &h[0..8],
        &h[8..12],
        &h[12..16],
        &h[16..20],
        &h[20..32]
    ))
}

fn hex(bytes: &[u8]) -> String {
    bytes
        .iter()
        .fold(String::with_capacity(bytes.len() * 2), |mut out, b| {
            // Writing to a String cannot fail.
            let _ = write!(out, "{b:02x}");
            out
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_is_64_lowercase_hex_and_unique() {
        let a = session_token().unwrap();
        let b = session_token().unwrap();
        assert_eq!(a.len(), 64);
        assert!(
            a.chars()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
        );
        assert_ne!(a, b);
    }

    #[test]
    fn uuid_matches_v4_pattern() {
        let re = regress::Regex::new(
            "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        )
        .unwrap();
        for _ in 0..200 {
            let id = uuid_v4().unwrap();
            assert!(re.find(&id).is_some(), "{id}");
        }
    }
}
