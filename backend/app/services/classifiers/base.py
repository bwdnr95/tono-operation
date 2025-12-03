from abc import ABC, abstractmethod

from backend.app.domain.email_message import IncomingMessage, ClassificationResult


class MessageClassifier(ABC):
    @abstractmethod
    def classify(self, message: IncomingMessage) -> ClassificationResult:
        raise NotImplementedError