// No console window in release builds on Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() -> std::process::ExitCode {
    match ev_lib::run() {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(e) => {
            // Logging may not be set up yet; stderr is the only channel left.
            eprintln!("EV failed to start: {e}");
            std::process::ExitCode::FAILURE
        }
    }
}
