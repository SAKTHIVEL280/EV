-- 001: timers, reminders and alarms (F-108); the action log (F-111).
-- Times are ISO 8601 in UTC.

CREATE TABLE timers (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('timer', 'reminder', 'alarm')),
    label TEXT NOT NULL,
    due_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'fired', 'cancelled', 'missed'))
);

CREATE INDEX timers_pending ON timers (state, due_at);

CREATE TABLE action_log (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    tool TEXT NOT NULL,
    summary TEXT NOT NULL,
    undo TEXT,
    undone INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX action_log_at ON action_log (at);
