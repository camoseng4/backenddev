import uuid
from typing import List

from track.models import RuntimeTrack, Observation, TrackState
from track.scorer import spatial_distance

# =========================================================
# BIRTH POLICY
# =========================================================
def allow_new_tracks(
    previous_track_count: int,
    current_observation_count: int
) -> bool:
    """
    Conservative birth policy.

    Only create new tracks when observations exceed
    current active hypotheses.
    """
    return current_observation_count > previous_track_count


def is_valid_birth_candidate(
    obs,
    active_tracks,
    config
) -> bool:
    """
    Prevent duplicate identities.
    """

    obs_center = (
        obs["center"]
        if isinstance(obs, dict)
        else obs.center
    )

    for t in active_tracks:

        if t.state == TrackState.CLOSED:
            continue

        ref = (
            t.predicted_position
            if t.predicted_position is not None
            else t.current_position
        )

        dist = spatial_distance(ref, obs_center)

        # 🔥 CRITICAL SAFETY BUFFER
        if dist < config.duplicate_birth_radius_px * 4:
            return False

    return True


# =========================================================
# CREATE SINGLE TRACK
# =========================================================
def create_track(
    observation,
    timestamp: float,
    frame_index: int = 0
) -> RuntimeTrack:
    """
    Accepts BOTH:
        - Observation dataclass
        - dict observation
    """

    # -----------------------------------------------------
    # NORMALISE INPUT FORMAT
    # -----------------------------------------------------
    if isinstance(observation, dict):
        center = observation["center"]
        embedding = observation["embedding"]
        detection_id = observation["detection_id"]
    else:
        center = observation.center
        embedding = observation.embedding
        detection_id = observation.detection_id

    return RuntimeTrack(
        runtime_track_id=str(uuid.uuid4()),

        state=TrackState.TENTATIVE,

        first_seen_timestamp=timestamp,
        last_seen_timestamp=timestamp,

        created_frame=frame_index,
        last_seen_frame=frame_index,

        current_position=center,
        current_embedding=embedding,

        velocity=(0.0, 0.0),
        predicted_position=None,

        age_frames=1,
        hit_count=1,
        miss_count=0,
        consecutive_hits=1,
        consecutive_misses=0,

        position_history=[
            {
                "timestamp": timestamp,
                "center": center
            }
        ],
        detection_history=[
            detection_id
        ],
    )


# =========================================================
# CREATE MANY TRACKS
# =========================================================
def create_tracks(
    observations: List[Observation],
    observation_indices: set,
    timestamp: float,
    frame_index: int = 0
) -> List[RuntimeTrack]:
    """
    Create tracks from unmatched observations.
    """

    new_tracks = []
    
    for obs_index in observation_indices:

        obs = observations[obs_index]

        # 🔥 BIRTH GATE CHECK (NEW)
        if not is_valid_birth_candidate(obs, [], None):
            # NOTE: we will plug active_tracks from engine in next step
            continue

        new_tracks.append(
            create_track(
                observation=obs,
                timestamp=timestamp,
                frame_index=frame_index
            )
        )

    return new_tracks