from typing import List
from track.models import RuntimeTrack, TrackState


# =========================================================
# SHOULD CLOSE TRACK
# =========================================================
def should_close_track(
    track: RuntimeTrack,
    current_timestamp: float,
    max_inactive_seconds: float,
    max_misses: int
) -> bool:
    """
    Decide whether a track should be permanently closed.
    """

    # CLOSED is already terminal
    if track.state == TrackState.CLOSED:
        return False

    inactive_seconds = current_timestamp - track.last_seen_timestamp

    return (
        inactive_seconds > max_inactive_seconds
        or track.miss_count > max_misses
    )


# =========================================================
# CLOSE TRACK
# =========================================================
def close_track(
    track: RuntimeTrack,
    current_timestamp: float,
    frame_index: int
) -> None:
    """
    Transition track into CLOSED state.
    """

    if track.state == TrackState.CLOSED:
        return

    track.state = TrackState.CLOSED
    track.closed_timestamp = current_timestamp
    track.closed_frame = frame_index


# =========================================================
# CLOSE EXPIRED TRACKS
# =========================================================
def close_expired_tracks(
    tracks: List[RuntimeTrack],
    current_timestamp: float,
    frame_index: int,
    max_inactive_seconds: float,
    max_misses: int
) -> None:
    """
    Scan and close stale tracks.
    """

    for t in tracks:
        if should_close_track(
            t,
            current_timestamp,
            max_inactive_seconds,
            max_misses
        ):
            close_track(t, current_timestamp, frame_index)


from track.models import TrackState


def get_active_tracks(tracks):
    """
    Backward-compatible helper for old engine code.

    Returns only ACTIVE tracks.
    """

    return [
        t for t in tracks
        if t.state == TrackState.ACTIVE
    ]