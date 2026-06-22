from track.models import RuntimeTrack
from track.history import recent_positions
from track.scorer import spatial_distance


# =========================================================
# AGE
# =========================================================
def age_seconds(
    track: RuntimeTrack
) -> float:
    """
    Lifetime duration.
    """

    return (
        track.last_seen_timestamp -
        track.first_seen_timestamp
    )


# =========================================================
# TRACK STRENGTH
# =========================================================
def track_strength(
    track: RuntimeTrack
) -> int:
    """
    Simple confidence estimate.
    """

    return (
        track.hit_count -
        track.miss_count
    )


# =========================================================
# CONFIRMATION
# =========================================================
def is_confirmed(
    track: RuntimeTrack,
    min_hits: int = 3
) -> bool:
    """
    Mature tracks are trusted more heavily.
    """

    return (
        track.hit_count >= min_hits
    )


# =========================================================
# CURRENT SPEED
# =========================================================
def current_speed(
    track: RuntimeTrack
) -> float:
    """
    Velocity magnitude.
    """

    vx, vy = track.velocity

    return (
        vx * vx +
        vy * vy
    ) ** 0.5


# =========================================================
# TOTAL DISTANCE
# =========================================================
def distance_travelled(
    track: RuntimeTrack
) -> float:
    """
    Total trajectory length.
    """

    history = track.position_history

    if len(history) < 2:
        return 0.0

    distance = 0.0

    for i in range(1, len(history)):

        distance += spatial_distance(
            history[i - 1]["center"],
            history[i]["center"]
        )

    return distance


# =========================================================
# AVERAGE SPEED
# =========================================================
def average_speed(
    track: RuntimeTrack
) -> float:
    """
    Average speed over lifetime.
    """

    duration = age_seconds(track)

    if duration <= 1e-6:
        return 0.0

    return (
        distance_travelled(track) /
        duration
    )


# =========================================================
# STATIONARY
# =========================================================
def is_stationary(
    track: RuntimeTrack,
    threshold: float = 5.0
) -> bool:
    """
    Determine if object is nearly stationary.
    """

    return (
        current_speed(track) < threshold
    )


# =========================================================
# VISIBILITY RATIO
# =========================================================
def visibility_ratio(
    track: RuntimeTrack
) -> float:
    """
    Fraction of frames successfully matched.
    """

    total = (
        track.hit_count +
        track.miss_count
    )

    if total == 0:
        return 0.0

    return (
        track.hit_count /
        total
    )


# =========================================================
# MOTION CONFIDENCE
# =========================================================
def motion_confidence(
    track: RuntimeTrack
) -> float:
    """
    Blend maturity and visibility.
    """

    maturity = min(
        track.hit_count / 20.0,
        1.0
    )

    visibility = visibility_ratio(
        track
    )

    return (
        maturity *
        visibility
    )