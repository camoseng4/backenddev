from typing import Optional, Set

from track.models import RuntimeTrack
from track.predictor import update_motion_state
from track.scorer import spatial_distance
from track.track_update import update_matched_track


# =========================================================
# FIND RECOVERY CANDIDATE
# =========================================================
def find_recovery_candidate(
    observation,
    active_tracks,
    config
) -> Optional[RuntimeTrack]:
    """
    Attempt to rescue an unmatched observation by attaching
    it to a recently missed active track.

    Existing trajectories are preferred over creating
    new identities.
    """

    best_track = None
    best_distance = float("inf")

    for track in active_tracks:

        if track.status != "ACTIVE":
            continue

        # only recover tracks that have actually missed
        if track.miss_count == 0:
            continue

        reference_position = (
            track.predicted_position
            if track.predicted_position is not None
            else track.current_position
        )

        distance = spatial_distance(
            reference_position,
            observation["center"]
        )

        if distance > config.max_distance * 2.0:
            continue

        if distance < best_distance:

            best_distance = distance
            best_track = track

    return best_track


# =========================================================
# RECOVER OBSERVATIONS
# =========================================================
def recover_unmatched_observations(
    unmatched_observations,
    observations,
    active_tracks,
    timestamp: float,
    config,
    velocity_smoothing: float
) -> Set[int]:
    """
    Attempt continuity recovery.

    Returns
    -------
    Set[int]

        Observation indices successfully rescued.
    """

    rescued_observations = set()

    for obs_index in unmatched_observations:

        observation = observations[obs_index]

        track = find_recovery_candidate(
            observation,
            active_tracks,
            config
        )

        if track is None:
            continue

        update_matched_track(
            track=track,
            observation=observation,
            timestamp=timestamp,
            velocity_smoothing=velocity_smoothing
        )

        rescued_observations.add(
            obs_index
        )

    return rescued_observations