"""Alert channel interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Alert:
    severity: Severity
    title: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    asset: str | None = None
    correlation_id: str | None = None


class Channel(ABC):
    """Abstract alert channel."""

    @abstractmethod
    def send(self, alert: Alert) -> bool:
        """Dispatch *alert* to the channel. Return True on success."""
