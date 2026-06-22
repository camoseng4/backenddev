from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict
import numpy as np


# =========================================================
# TRACK STATE
# =========================================================
class TrackState(str, Enum):
    TENTATIVE = "TENTATIVE"
    ACTIVE = "ACTIVE"
    LOST = "LOST"
    CLOSED = "CLOSED"


# =========================================================
# OBSERVATION
# =========================================================
@dataclass
class Observation:
    detection_id: str
    timestamp: float
    center: Tuple[float, float]
    embedding: np.ndarray


# =========================================================
# RUNTIME TRACK (CANONICAL)
# =========================================================
@dataclass
class RuntimeTrack:

    # identity
    runtime_track_id: str

    # lifecycle
    state: TrackState = TrackState.TENTATIVE

    # timing
    first_seen_timestamp: float = 0.0
    last_seen_timestamp: float = 0.0

    created_frame: int = 0
    last_seen_frame: int = 0

    closed_timestamp: Optional[float] = None
    closed_frame: Optional[int] = None

    # state
    current_position: Tuple[float, float] = (0.0, 0.0)
    current_embedding: Optional[np.ndarray] = None

    # motion
    velocity: Tuple[float, float] = (0.0, 0.0)
    speed_pixels_per_second: float = 0.0
    predicted_position: Optional[Tuple[float, float]] = None

    # stats
    age_frames: int = 1
    hit_count: int = 1
    miss_count: int = 0
    consecutive_hits: int = 1
    consecutive_misses: int = 0

    # history
    position_history: List[dict] = field(default_factory=list)
    detection_history: List[str] = field(default_factory=list)

    # =====================================================
    # STATE HELPERS
    # =====================================================
    def is_active(self) -> bool:
        return self.state == TrackState.ACTIVE

    def is_lost(self) -> bool:
        return self.state == TrackState.LOST

    def is_tentative(self) -> bool:
        return self.state == TrackState.TENTATIVE

    def is_closed(self) -> bool:
        return self.state == TrackState.CLOSED

    def is_matchable(self) -> bool:
        return self.state != TrackState.CLOSED

    # =====================================================
    # UPDATES
    # =====================================================
    def register_match(self, timestamp: float, frame_index: int):

        self.last_seen_timestamp = timestamp
        self.last_seen_frame = frame_index

        self.hit_count += 1
        self.consecutive_hits += 1

        self.miss_count = 0
        self.consecutive_misses = 0

        self.age_frames += 1

    def register_miss(self):

        self.miss_count += 1
        self.consecutive_misses += 1

        self.consecutive_hits = 0
        self.age_frames += 1

    def promote(self):
        if self.state != TrackState.CLOSED:
            self.state = TrackState.ACTIVE

    def mark_lost(self):
        if self.state != TrackState.CLOSED:
            self.state = TrackState.LOST

    def close(self, timestamp: float, frame_index: int):

        self.state = TrackState.CLOSED
        self.closed_timestamp = timestamp
        self.closed_frame = frame_index