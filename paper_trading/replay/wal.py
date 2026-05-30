"""Write-Ahead Log — durable decision-chain capture for deterministic replay.

The WAL records every step in the trading decision chain as an ordered event
stream. Each event captures both the input context and the output decision,
enabling full causal reconstruction of engine state.

Event types (decision chain):
    price_update      — OHLC bar data received
    feature_computed  — feature vector for an asset
    signal_generated  — model signal (entry/flat/exit + confidence)
    risk_approved     — risk gate decision
    entry_executed    — fill result for position entry
    sl_executed       — fill result for stop-loss
    tp_executed       — fill result for take-profit
    position_closed   — position closed (any reason)
    state_committed   — full state snapshot checkpoint
    actor_health      — actor health state change

Invariants:
    I1: Events from a single source are strictly ordered by sequence.
    I2: All events are deterministic — same inputs → identical payload.
    I3: WAL writer is append-only; past events are never mutated.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("quantforge.replay.wal")

WAL_DIR = "data/live/wal"


@dataclass
class WalEvent:
    """Single event in the write-ahead log."""

    sequence: int
    source: str
    event_type: str
    timestamp: str = ""
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sequence": self.sequence,
            "source": self.source,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict) -> WalEvent:
        return cls(
            sequence=d["sequence"],
            source=d["source"],
            event_type=d["event_type"],
            timestamp=d.get("timestamp", ""),
            payload=d.get("payload", {}),
        )


# ── WAL Writer ──────────────────────────────────────────────────────────────


class WalWriter:
    """Thread-safe, append-only WAL writer.

    Writes one JSON object per line (JSONL format).
    Each event is flushed to disk immediately for crash safety.
    Past events are never mutated (invariant I3).
    """

    def __init__(self, base_dir: str, source: str = "engine"):
        self._base_dir = base_dir
        self._source = source
        self._seq = 0
        self._lock = threading.Lock()
        self._path = os.path.join(base_dir, WAL_DIR, f"{source}.jsonl")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    def write(self, event_type: str, payload: dict) -> WalEvent:
        """Append a single event to the WAL. Returns the created event."""
        with self._lock:
            self._seq += 1
            event = WalEvent(
                sequence=self._seq,
                source=self._source,
                event_type=event_type,
                timestamp=datetime.now(timezone.utc).isoformat(),
                payload=payload,
            )
            line = json.dumps(event.to_dict(), default=str) + "\n"
            with open(self._path, "a") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        return event

    @property
    def current_sequence(self) -> int:
        return self._seq

    @property
    def path(self) -> str:
        return self._path


# ── WAL Reader ──────────────────────────────────────────────────────────────


class WalReader:
    """Read and iterate over WAL events. Supports replay from sequence offsets."""

    def __init__(self, base_dir: str, source: str = "engine"):
        self._path = os.path.join(base_dir, WAL_DIR, f"{source}.jsonl")

    def read_all(self) -> list[WalEvent]:
        """Read all events from the WAL."""
        return list(self._iter_events())

    def read_from(self, seq: int) -> list[WalEvent]:
        """Read all events with sequence >= seq."""
        return [e for e in self._iter_events() if e.sequence >= seq]

    def read_last(self, n: int = 10) -> list[WalEvent]:
        """Read the last N events."""
        events = self.read_all()
        return events[-n:]

    def count(self) -> int:
        """Return total event count (fast — reads line count only)."""
        if not os.path.exists(self._path):
            return 0
        with open(self._path) as f:
            return sum(1 for _ in f)

    def _iter_events(self):
        if not os.path.exists(self._path):
            return
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield WalEvent.from_dict(json.loads(line))
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning("WAL parse error: %s", e)
