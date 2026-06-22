import uuid
from typing import Dict, List, Tuple, Set

import numpy as np

from track.models import RuntimeTrack
from track.matcher import match_tracks
from track.predictor import update_prediction, update_motion_state
from track.contracts import TrackerConfig
from track.models import TrackState


# =========================================================
# MAIN TRACKING PIPELINE
# =========================================================
def track(
    observations_by_ts: Dict[float, List[dict]],
    active_tracks: List[RuntimeTrack],
    config: TrackerConfig
):
    """
    Minimal stable tracker pipeline.

    Guarantees:
        - no crashes
        - consistent state model
        - dict-based observations
        - stable matching loop
    """

    # -----------------------------------------------------
    # Track registry (global memory)
    # -----------------------------------------------------
    all_tracks: Dict[str, RuntimeTrack] = {
        t.runtime_track_id: t for t in active_tracks
    }

    timestamps = sorted(observations_by_ts.keys())

    # =====================================================
    # FRAME LOOP
    # =====================================================
    for ts in timestamps:

        observations = observations_by_ts[ts]

        # active tracks only
        active = [
            t for t in all_tracks.values()
            if t.state == TrackState.ACTIVE
        ]

        # -------------------------------------------------
        # PREDICT STEP
        # -------------------------------------------------
        for t in active:
            update_prediction(track=t,current_timestamp=ts,config=config)

        # -------------------------------------------------
        # MATCHING
        # -------------------------------------------------
        matches, unmatched_tracks, unmatched_obs = match_tracks(
            observations=observations,
            tracks=active,
            config=config
        )

        # =================================================
        # APPLY MATCHES
        # =================================================
        for ti, oi in matches:

            track_obj = active[ti]
            obs = observations[oi]

            new_pos = obs["center"]

            update_motion_state(
                track=t,
                new_position=new_pos,
                current_timestamp=ts,
                config=config
            )

            track_obj.current_embedding = obs["embedding"]
            track_obj.last_seen_timestamp = ts

            track_obj.hit_count += 1
            track_obj.miss_count = 0
            track_obj.age_frames += 1

            track_obj.position_history.append({
                "timestamp": ts,
                "center": new_pos
            })

            track_obj.detection_history.append(obs["detection_id"])

            # promote after first confirmations
            if track_obj.hit_count >= config.young_track_hits:
                track_obj.state = "ACTIVE"

        # =================================================
        # HANDLE MISSES
        # =================================================
        for ti in unmatched_tracks:
            t = active[ti]
            t.miss_count += 1
            t.age_frames += 1

        # =================================================
        # CREATE NEW TRACKS
        # =================================================
        used_obs: Set[int] = {oi for _, oi in matches}

        for oi in unmatched_obs:

            if oi in used_obs:
                continue

            obs = observations[oi]

            new_track = RuntimeTrack(
                runtime_track_id=str(uuid.uuid4()),

                state="TENTATIVE",

                first_seen_timestamp=ts,
                last_seen_timestamp=ts,

                created_frame=0,
                last_seen_frame=0,

                current_position=obs["center"],
                current_embedding=obs["embedding"],

                velocity=(0.0, 0.0),
                predicted_position=None,

                age_frames=1,
                hit_count=1,
                miss_count=0,

                consecutive_hits=1,
                consecutive_misses=0,

                position_history=[{
                    "timestamp": ts,
                    "center": obs["center"]
                }],

                detection_history=[obs["detection_id"]],
            )

            all_tracks[new_track.runtime_track_id] = new_track

        # =================================================
        # CLOSE OLD TRACKS
        # =================================================
        for t in all_tracks.values():

            if t.state == "CLOSED":
                continue

            inactive_time = ts - t.last_seen_timestamp

            if (
                t.miss_count > config.max_misses
                or inactive_time > config.max_inactive_seconds
            ):
                t.state = "CLOSED"

    # =====================================================
    # OUTPUT
    # =====================================================
    active_tracks_out = [
        t for t in all_tracks.values()
        if t.state != "CLOSED"
    ]

    return list(all_tracks.values()), active_tracks_out