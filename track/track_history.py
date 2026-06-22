from typing import List, Tuple

from track.models import RuntimeTrack


# =========================================================
# POSITION HISTORY
# =========================================================
def add_position(
    track: RuntimeTrack,
    timestamp: float,
    position: Tuple[float, float]
) -> None:
    """
    Append a position sample.
    """

    track.position_history.append(
        {
            "timestamp": timestamp,
            "center": position
        }
    )


# =========================================================
# DETECTION HISTORY
# =========================================================
def add_detection(
    track: RuntimeTrack,
    detection_id: str
) -> None:
    """
    Append detection id.
    """

    track.detection_history.append(
        detection_id
    )


# =========================================================
# RECENT POSITIONS
# =========================================================
def recent_positions(
    track: RuntimeTrack,
    n: int = 10
) -> List[Tuple[float, float]]:
    """
    Return the most recent N positions.
    """

    history = track.position_history[-n:]

    return [
        sample["center"]
        for sample in history
    ]


# =========================================================
# RECENT TIMESTAMPS
# =========================================================
def recent_timestamps(
    track: RuntimeTrack,
    n: int = 10
):
    """
    Return recent timestamps.
    """

    history = track.position_history[-n:]

    return [
        sample["timestamp"]
        for sample in history
    ]


# =========================================================
# TRAJECTORY LENGTH
# =========================================================
def trajectory_length(
    track: RuntimeTrack
) -> int:
    """
    Number of stored position samples.
    """

    return len(
        track.position_history
    )


# =========================================================
# HISTORY SIZE
# =========================================================
def history_size(
    track: RuntimeTrack
) -> int:
    """
    Alias for trajectory size.
    """

    return len(
        track.position_history
    )


# =========================================================
# KEEP RECENT HISTORY
# =========================================================
def prune_history(
    track: RuntimeTrack,
    max_points: int = 200
) -> None:
    """
    Prevent unlimited memory growth.

    Keeps only the newest samples.
    """

    if len(track.position_history) > max_points:

        track.position_history = (
            track.position_history[-max_points:]
        )

    if len(track.detection_history) > max_points:

        track.detection_history = (
            track.detection_history[-max_points:]
        )


# =========================================================
# FIRST POSITION
# =========================================================
def first_position(
    track: RuntimeTrack
):
    """
    First observed location.
    """

    if not track.position_history:
        return None

    return track.position_history[0]["center"]


# =========================================================
# LAST POSITION
# =========================================================
def last_position(
    track: RuntimeTrack
):
    """
    Most recent observed location.
    """

    if not track.position_history:
        return None

    return track.position_history[-1]["center"]