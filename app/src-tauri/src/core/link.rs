//! Sending messages to core while a session is connected.
//!
//! The session attaches a channel after the handshake and detaches it when it
//! ends. Sending while core is down fails at once instead of queueing work for
//! a core that may never come back.

use std::sync::Mutex;

use tokio::sync::mpsc::{UnboundedReceiver, UnboundedSender, unbounded_channel};

use crate::protocol::Message;

#[derive(Debug, Default)]
pub struct CoreLink {
    sender: Mutex<Option<UnboundedSender<Message>>>,
}

#[derive(Debug, PartialEq, Eq, thiserror::Error)]
#[error("core is not connected")]
pub struct NotConnected;

impl CoreLink {
    /// # Errors
    /// When no session is connected.
    pub fn send(&self, message: Message) -> Result<(), NotConnected> {
        let guard = self
            .sender
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        guard
            .as_ref()
            .ok_or(NotConnected)?
            .send(message)
            .map_err(|_| NotConnected)
    }

    pub(crate) fn attach(&self) -> UnboundedReceiver<Message> {
        let (tx, rx) = unbounded_channel();
        *self
            .sender
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(tx);
        rx
    }

    pub(crate) fn detach(&self) {
        *self
            .sender
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner) = None;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol;

    #[test]
    fn send_requires_attached_session() {
        let link = CoreLink::default();
        assert_eq!(link.send(protocol::ping().unwrap()), Err(NotConnected));
        let mut rx = link.attach();
        link.send(protocol::ping().unwrap()).unwrap();
        assert!(matches!(rx.try_recv(), Ok(Message::Ping(_))));
        link.detach();
        assert_eq!(link.send(protocol::ping().unwrap()), Err(NotConnected));
    }
}
