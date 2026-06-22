from typing import List, Dict, Any

from track.models import RuntimeTrack
from track.metrics import (
    age_seconds,
    track_strength,
    current_speed,
    distance_travelled,
    visibility_ratio
)


# =========================================================
# TRACK TO DICT
# =========================================================
def track_to_dict(
    track: RuntimeTrack
) -> Dict[str, Any]:
    """
    Serialise a track for debugging / logging.
    """

    return {
        "id": track.runtime_track_id,
        "status": track.status,
        "first_seen": track.first_seen_timestamp,
        "last_seen": track.last_seen_timestamp,

        "age_seconds": age_seconds(track),
        "strength": track_strength(track),

        "hits": track.hit_count,
        "misses": track.miss_count,

        "speed": current_speed(track),
        "distance": distance_travelled(track),

        "visibility": visibility_ratio(track),

        "position": track.current_position,
        "predicted": track.predicted_position,
    }


# =========================================================
# PRINT ACTIVE TRACKS
# =========================================================
def print_active_tracks(
    tracks: List[RuntimeTrack]
) -> None:
    """
    Print compact active track summary.
    """

    active = [
        t for t in tracks
        if t.status == "ACTIVE"
    ]

    print("\n=== ACTIVE TRACKS ===")

    for t in active:

        d = track_to_dict(t)

        print(
            f"[{d['id'][:6]}] "
            f"hits={d['hits']} "
            f"misses={d['misses']} "
            f"speed={d['speed']:.2f} "
            f"pos={d['position']}"
        )


# =========================================================
# PRINT CLOSED TRACKS
# =========================================================
def print_closed_tracks(
    tracks: List[RuntimeTrack]
) -> None:
    """
    Print closed tracks summary.
    """

    closed = [
        t for t in tracks
        if t.status == "CLOSED"
    ]

    print("\n=== CLOSED TRACKS ===")

    for t in closed:

        d = track_to_dict(t)

        print(
            f"[{d['id'][:6]}] "
            f"hits={d['hits']} "
            f"misses={d['misses']} "
            f"age={d['age_seconds']:.2f}s"
        )


# =========================================================
# TRACK SUMMARY
# =========================================================
def track_summary(
    tracks: List[RuntimeTrack]
) -> Dict[str, Any]:
    """
    High-level tracker statistics.
    """

    total = len(tracks)

    active = len([
        t for t in tracks
        if t.status == "ACTIVE"
    ])

    closed = len([
        t for t in tracks
        if t.status == "CLOSED"
    ])

    avg_strength = (
        sum(track_strength(t) for t in tracks) /
        total
        if total > 0 else 0.0
    )

    return {
        "total_tracks": total,
        "active": active,
        "closed": closed,
        "avg_strength": avg_strength
    }


# =========================================================
# DUMP STATE
# =========================================================
def dump_tracker_state(
    tracks: List[RuntimeTrack]
) -> Dict[str, Any]:
    """
    Full snapshot for logging / inspection.
    """

    return {
        "summary": track_summary(tracks),
        "tracks": [
            track_to_dict(t)
            for t in tracks
        ]
    }