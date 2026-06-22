import numpy as np
from typing import Tuple

from track.models import RuntimeTrack, TrackState


# ---------------------------------------------------------
# IMPOSSIBLE COST
# ---------------------------------------------------------
IMPOSSIBLE_COST = 1e6


# ---------------------------------------------------------
# COSINE SIMILARITY
# ---------------------------------------------------------
def cosine_similarity(
    a: np.ndarray,
    b: np.ndarray
) -> float:

    if a is None or b is None:
        return 0.0

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0

    a = a / norm_a
    b = b / norm_b

    return float(np.dot(a, b))


# ---------------------------------------------------------
# SPATIAL DISTANCE
# ---------------------------------------------------------
def spatial_distance(
    a: Tuple[float, float],
    b: Tuple[float, float]
) -> float:

    dx = a[0] - b[0]
    dy = a[1] - b[1]

    return (
        dx * dx +
        dy * dy
    ) ** 0.5


# ---------------------------------------------------------
# REFERENCE POSITION
# ---------------------------------------------------------
def reference_position(
    track: RuntimeTrack
) -> Tuple[float, float]:

    if track.predicted_position is not None:
        return track.predicted_position

    return track.current_position


# ---------------------------------------------------------
# DYNAMIC MOTION GATE
# ---------------------------------------------------------
def dynamic_motion_gate(
    track: RuntimeTrack,
    dt: float,
    config
) -> float:
    """
    Gate expands with velocity uncertainty.

    But never grows without bound.
    """

    gate = (
        config.base_motion_gate_px
        +
        config.velocity_uncertainty_px_per_second * dt
    )

    return min(
        gate,
        config.max_motion_gate_px
    )


# ---------------------------------------------------------
# TEMPORAL GATE
# ---------------------------------------------------------
def passes_temporal_gate(
    track: RuntimeTrack,
    timestamp: float,
    config
) -> bool:

    if track.state == TrackState.CLOSED:
        return False

    dt = max(
        timestamp - track.last_seen_timestamp,
        0.0
    )

    if track.state == TrackState.ACTIVE:

        return (
            dt <= config.max_active_gap_seconds
        )

    if track.state == TrackState.LOST:

        return (
            dt <= config.max_lost_seconds
        )

    if track.state == TrackState.TENTATIVE:

        return (
            dt <= config.max_tentative_seconds
        )

    return False


# ---------------------------------------------------------
# MOTION GATE
# ---------------------------------------------------------
def passes_motion_gate(
    track: RuntimeTrack,
    obs,
    config
) -> bool:

    ref_pos = reference_position(track)

    dt = max(
        obs["timestamp"] -
        track.last_seen_timestamp,
        0.0
    )

    allowed_distance = dynamic_motion_gate(
        track,
        dt,
        config
    )

    dist = spatial_distance(
        ref_pos,
        obs["center"]
    )

    return dist <= allowed_distance


# ---------------------------------------------------------
# APPEARANCE SCORE
# ---------------------------------------------------------
def appearance_score(
    track: RuntimeTrack,
    obs
) -> float:

    if track.current_embedding is None:
        return 0.5

    sim = cosine_similarity(
        track.current_embedding,
        obs["embedding"]
    )

    return (
        sim + 1.0
    ) / 2.0


# ---------------------------------------------------------
# SPATIAL SCORE
# ---------------------------------------------------------
def spatial_score(
    distance: float,
    gate_distance: float
) -> float:

    x = distance / max(
        gate_distance,
        1e-6
    )

    return float(
        np.exp(
            -4.0 * x
        )
    )


# ---------------------------------------------------------
# LOST AGE PENALTY
# ---------------------------------------------------------
def lost_penalty(
    track: RuntimeTrack
) -> float:
    """
    Lost tracks become increasingly
    unattractive.
    """

    if track.state != TrackState.LOST:
        return 0.0

    return min(
        0.5,
        0.05 * track.consecutive_misses
    )


# ---------------------------------------------------------
# ELIGIBILITY
# ---------------------------------------------------------
def pair_is_eligible(
    track: RuntimeTrack,
    obs,
    config
) -> bool:
    """
    Hard gates.

    Impossible pairs never enter
    the Hungarian matrix.
    """

    if track.state == TrackState.CLOSED:
        return False

    if not passes_temporal_gate(
        track,
        obs["timestamp"],
        config
    ):
        return False

    if not passes_motion_gate(
        track,
        obs,
        config
    ):
        return False

    return True


# ---------------------------------------------------------
# MATCH COST
# ---------------------------------------------------------
def match_cost(
    track: RuntimeTrack,
    obs,
    config
) -> float:
    """
    Lower is better.

    Invalid pairs become IMPOSSIBLE_COST.
    """

    if not pair_is_eligible(
        track,
        obs,
        config
    ):
        return IMPOSSIBLE_COST

    ref_pos = reference_position(track)

    distance = spatial_distance(
        ref_pos,
        obs["center"]
    )

    gate_distance = dynamic_motion_gate(
        track,
        obs["timestamp"] -
        track.last_seen_timestamp,
        config
    )

    spatial = spatial_score(
        distance,
        gate_distance
    )

    appearance = appearance_score(
        track,
        obs
    )

    cost = (
        config.spatial_weight *
        (1.0 - spatial)
        +
        config.appearance_weight *
        (1.0 - appearance)
    )

    cost += lost_penalty(track)

    if track.state == TrackState.TENTATIVE:
        cost += 0.05

    return float(cost)


# ---------------------------------------------------------
# MATCH SCORE
# ---------------------------------------------------------
def score_match(
    track: RuntimeTrack,
    obs,
    config
) -> float:
    """
    Compatibility wrapper.

    Higher score is better.
    """

    cost = match_cost(
        track,
        obs,
        config
    )

    if cost >= IMPOSSIBLE_COST:
        return 0.0

    return max(
        0.0,
        1.0 - cost
    )