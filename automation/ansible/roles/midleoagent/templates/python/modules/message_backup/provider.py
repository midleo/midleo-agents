from abc import ABC, abstractmethod


class MessageBackupProvider(ABC):
    """Broker-specific message receive/ack adapter."""

    @abstractmethod
    def connect(self):
        """Open broker connection."""

    @abstractmethod
    def check_health(self):
        """Return True when broker connection is usable."""

    @abstractmethod
    def receive(self, max_messages, timeout_ms, body_mode):
        """Yield raw broker messages up to max_messages within timeout_ms."""

    @abstractmethod
    def ack(self, message):
        """Acknowledge/commit a previously received message."""

    @abstractmethod
    def nack(self, message, requeue=True):
        """Negative-acknowledge; requeue when supported."""

    @abstractmethod
    def close(self):
        """Release broker resources."""
