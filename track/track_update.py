from track.models import RuntimeTrack
from track.predictor import update_motion_state
from track.track_state import (
    set_embedding,
    update_last_seen,
    register_match,
    register_miss,
    append_position_history,
    append_detection_history
)


# =========================================================
# MATCH UPDATE
# =========================================================
def update_matched_track(
    track: RuntimeTrack,
    observation,
    timestamp: float,
    velocity_smoothing: float
) -> None:
    """
    Apply a successful observation assignment.

    Responsibilities:

        1. Update motion state.
        2. Update appearance.
        3. Update timestamps.
        4. Reset miss counter.
        5. Update history.
    """

    update_motion_state(
        track=track,
        new_position=observation["center"],
        current_timestamp=timestamp,
        smoothing_factor=velocity_smoothing
    )

    set_embedding(
        track,
        observation["embedding"]
    )

    update_last_seen(
        track,
        timestamp
    )

    register_match(
        track
    )

    append_position_history(
        track,
        timestamp,
        observation["center"]
    )

    append_detection_history(
        track,
        observation["detection_id"]
    )


# =========================================================
# MISS UPDATE
# =========================================================
def update_missed_track(
    track: RuntimeTrack
) -> None:
    """
    Track was not assigned an observation.

    Increase miss count and age.
    """

    register_miss(
        track
    )


# =========================================================
# BATCH MATCH UPDATE
# =========================================================
def update_matches(
    matches,
    tracks,
    observations,
    timestamp: float,
    velocity_smoothing: float
) -> None:
    """
    Update all successful assignments.
    """

    for track_index, obs_index in matches:

        update_matched_track(
            track=tracks[track_index],
            observation=observations[obs_index],
            timestamp=timestamp,
            velocity_smoothing=velocity_smoothing
        )


# =========================================================
# BATCH MISS UPDATE
# =========================================================
def update_misses(
    unmatched_track_indices,
    tracks
) -> None:
    """
    Update all unmatched tracks.
    """

    for track_index in unmatched_track_indices:

        update_missed_track(
            tracks[track_index]
        )