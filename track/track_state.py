from typing import Tuple

from track.models import RuntimeTrack


# =========================================================
# POSITION
# =========================================================
def set_position(
    track: RuntimeTrack,
    position: Tuple[float, float]
) -> None:
    """
    Update current observed position.
    """

    track.current_position = position


# =========================================================
# PREDICTION
# =========================================================
def set_prediction(
    track: RuntimeTrack,
    prediction: Tuple[float, float]
) -> None:
    """
    Store predicted position.
    """

    track.predicted_position = prediction


def clear_prediction(
    track: RuntimeTrack
) -> None:
    """
    Prediction is invalid after a successful update.
    """

    track.predicted_position = None


# =========================================================
# VELOCITY
# =========================================================
def set_velocity(
    track: RuntimeTrack,
    velocity: Tuple[float, float]
) -> None:
    """
    Replace current velocity estimate.
    """

    track.velocity = velocity


# =========================================================
# EMBEDDING
# =========================================================
def set_embedding(
    track: RuntimeTrack,
    embedding
) -> None:
    """
    Store latest appearance descriptor.
    """

    track.current_embedding = embedding


# =========================================================
# TIMESTAMPS
# =========================================================
def update_last_seen(
    track: RuntimeTrack,
    timestamp: float
) -> None:
    """
    Update last observation timestamp.
    """

    track.last_seen_timestamp = timestamp


def update_prediction_timestamp(
    track: RuntimeTrack,
    timestamp: float
) -> None:
    """
    Record prediction timestamp.
    """

    track.last_prediction_timestamp = timestamp


# =========================================================
# MATCHES
# =========================================================
def register_match(
    track: RuntimeTrack
) -> None:
    """
    Successful association.
    """

    track.hit_count += 1
    track.age_frames += 1

    track.miss_count = 0

    track.consecutive_matches += 1


# =========================================================
# MISSES
# =========================================================
def register_miss(
    track: RuntimeTrack
) -> None:
    """
    Failed association.
    """

    track.age_frames += 1

    track.miss_count += 1

    track.consecutive_matches = 0


# =========================================================
# HISTORY
# =========================================================
def append_position_history(
    track: RuntimeTrack,
    timestamp: float,
    position: Tuple[float, float]
) -> None:
    """
    Store position history.
    """

    track.position_history.append(
        {
            "timestamp": timestamp,
            "center": position
        }
    )


def append_detection_history(
    track: RuntimeTrack,
    detection_id: str
) -> None:
    """
    Store source detection ids.
    """

    track.detection_history.append(
        detection_id
    )


# =========================================================
# STATUS
# =========================================================
def activate_track(
    track: RuntimeTrack
) -> None:
    """
    Mark active.
    """

    track.status = "ACTIVE"


def close_track(
    track: RuntimeTrack
) -> None:
    """
    Permanently close track.
    """

    track.status = "CLOSED"


# =========================================================
# STRENGTH
# =========================================================
def increase_single_frame_lock_counter(
    track: RuntimeTrack
) -> None:
    track.consecutive_single_frame_lock += 1


def reset_single_frame_lock_counter(
    track: RuntimeTrack
) -> None:
    track.consecutive_single_frame_lock = 0


# =========================================================
# FRAME COUNTERS
# =========================================================
def increment_frames_since_birth(
    track: RuntimeTrack
) -> None:
    track.frames_since_birth += 1


def set_last_observation_count(
    track: RuntimeTrack,
    count: int
) -> None:
    track.last_observation_count = count