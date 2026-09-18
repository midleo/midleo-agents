from abc import ABC, abstractmethod


class MessageBackupProvider(ABC):
    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def check_health(self):
        pass

    @abstractmethod
    def receive(self, max_messages, timeout_ms, body_mode):
        pass

    @abstractmethod
    def ack(self, message):
        pass

    @abstractmethod
    def nack(self, message, requeue=True):
        pass

    @abstractmethod
    def close(self):
        pass
