//! PC-tool messages for the island: confirmations (F-418), the action log's
//! Undo (F-111), timers firing (F-108) and focus mode (F-109).

use serde::Serialize;
use specta::Type;

use crate::protocol::Message;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Type)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum PcUpdateKind {
    /// A step waits for the user's yes or no.
    Confirm {
        turn_id: String,
        request_id: String,
        tool: String,
        question: String,
        /// confirm | dangerous
        risk: String,
    },
    /// The question is gone (answered, timed out or cancelled).
    ConfirmClosed {
        request_id: String,
        allowed: bool,
    },
    /// An action changed something; `undoable` shows the Undo button.
    Action {
        turn_id: String,
        action_id: u32,
        tool: String,
        summary: String,
        undoable: bool,
    },
    Undone {
        action_id: u32,
        ok: bool,
        message: String,
    },
    /// A timer, reminder or alarm came due.
    Timer {
        timer_id: u32,
        /// timer | reminder | alarm
        timer_kind: String,
        label: String,
        missed: bool,
    },
    Focus {
        on: bool,
        minutes: Option<u32>,
    },
    /// What the hotkey captured from the app the user was in (F-201); `text`
    /// is `None` when nothing was selected.
    Context {
        text: Option<String>,
        app: String,
        title: String,
    },
    /// Result of a quick action's Replace (F-202).
    Replaced {
        ok: bool,
        message: String,
    },
}

#[derive(Clone, Debug, Serialize, Type, tauri_specta::Event)]
pub struct PcUpdate(pub PcUpdateKind);

fn small(value: u64) -> u32 {
    u32::try_from(value).unwrap_or(u32::MAX)
}

/// Convert a PC message; `None` for anything else.
#[must_use]
pub fn update(message: Message) -> Option<PcUpdateKind> {
    Some(match message {
        Message::ToolConfirm(m) => PcUpdateKind::Confirm {
            turn_id: m.payload.turn_id.to_string(),
            request_id: m.payload.request_id.to_string(),
            tool: m.payload.tool.to_string(),
            question: m.payload.question.to_string(),
            risk: m.payload.risk.to_string(),
        },
        Message::ToolConfirmClosed(m) => PcUpdateKind::ConfirmClosed {
            request_id: m.payload.request_id.to_string(),
            allowed: m.payload.allowed,
        },
        Message::ActionRecorded(m) => PcUpdateKind::Action {
            turn_id: m.payload.turn_id.to_string(),
            action_id: small(m.payload.action_id.get()),
            tool: m.payload.tool.to_string(),
            summary: m.payload.summary.to_string(),
            undoable: m.payload.undoable,
        },
        Message::ActionUndone(m) => PcUpdateKind::Undone {
            action_id: small(m.payload.action_id),
            ok: m.payload.ok,
            message: m.payload.message.to_string(),
        },
        Message::TimerFired(m) => PcUpdateKind::Timer {
            timer_id: small(m.payload.timer_id.get()),
            timer_kind: m.payload.kind.to_string(),
            label: m.payload.label.to_string(),
            missed: m.payload.missed,
        },
        Message::FocusChanged(m) => PcUpdateKind::Focus {
            on: m.payload.on,
            minutes: m.payload.minutes.map(|n| small(n.get())),
        },
        Message::ContextCaptured(m) => PcUpdateKind::Context {
            text: m.payload.text.map(|t| t.to_string()),
            app: m.payload.app.map(|a| a.to_string()).unwrap_or_default(),
            title: m.payload.title.map(|t| t.to_string()).unwrap_or_default(),
        },
        Message::ContextReplaced(m) => PcUpdateKind::Replaced {
            ok: m.payload.ok,
            message: m.payload.message.to_string(),
        },
        _ => return None,
    })
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::path::Path;

    use super::*;
    use crate::protocol::decode;

    fn fixture(name: &str) -> Message {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../protocol/fixtures/valid")
            .join(name);
        decode(&fs::read_to_string(path).unwrap()).unwrap()
    }

    #[test]
    fn converts_every_pc_message() {
        assert_eq!(
            update(fixture("tool_confirm.json")),
            Some(PcUpdateKind::Confirm {
                turn_id: "36c14c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d".into(),
                request_id: "9b1c2d3e-4f50-4a6b-8c7d-8e9f0a1b2c3d".into(),
                tool: "apps".into(),
                question: "Close Notepad?".into(),
                risk: "confirm".into(),
            })
        );
        assert_eq!(
            update(fixture("tool_confirm_closed.json")),
            Some(PcUpdateKind::ConfirmClosed {
                request_id: "9b1c2d3e-4f50-4a6b-8c7d-8e9f0a1b2c3d".into(),
                allowed: false,
            })
        );
        assert!(matches!(
            update(fixture("action_recorded.json")),
            Some(PcUpdateKind::Action {
                action_id: 7,
                undoable: true,
                ..
            })
        ));
        assert!(matches!(
            update(fixture("action_undone.json")),
            Some(PcUpdateKind::Undone {
                action_id: 7,
                ok: true,
                ..
            })
        ));
        assert_eq!(
            update(fixture("timer_fired.json")),
            Some(PcUpdateKind::Timer {
                timer_id: 3,
                timer_kind: "reminder".into(),
                label: "call mom".into(),
                missed: false,
            })
        );
        assert_eq!(
            update(fixture("focus_changed.json")),
            Some(PcUpdateKind::Focus {
                on: true,
                minutes: Some(25),
            })
        );
        assert_eq!(
            update(fixture("context_captured.json")),
            Some(PcUpdateKind::Context {
                text: Some("teh quick brown fox".into()),
                app: "notepad".into(),
                title: "notes.txt - Notepad".into(),
            })
        );
        assert_eq!(
            update(fixture("context_captured_none.json")),
            Some(PcUpdateKind::Context {
                text: None,
                app: String::new(),
                title: String::new(),
            })
        );
        assert!(matches!(
            update(fixture("context_replaced.json")),
            Some(PcUpdateKind::Replaced { ok: true, .. })
        ));
        assert_eq!(update(fixture("ping.json")), None);
    }
}
