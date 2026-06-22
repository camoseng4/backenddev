from typing import List, Tuple, Set

from track.assignment import assign_tracks
from track.models import RuntimeTrack


def match_tracks(
    observations: List[dict],
    tracks: List[RuntimeTrack],
    config
) -> Tuple[
    List[Tuple[int, int]],
    Set[int],
    Set[int]
]:
    """
    Main matching orchestration layer.

    Responsibilities
    ----------------

    1. Receive active tracks and observations.
    2. Execute matching stages.
    3. Return:

        matches:
            [(track_index, observation_index)]

        unmatched_tracks:
            set[int]

        unmatched_observations:
            set[int]

    Philosophy
    ----------

    Motion continuity is primary.

    Appearance acts only as a tie-breaker.

    Global optimization is preferred over greedy decisions.

    This module intentionally separates matching
    strategy from the tracking engine.

    Future stages may include:

        Stage 1:
            Confirmed-track assignment.

        Stage 2:
            Tentative-track assignment.

        Stage 3:
            Appearance recovery.

        Stage 4:
            Lost-track recovery.

        Stage 5:
            Birth handling.
    """

    # -----------------------------------------------------
    # Empty cases
    # -----------------------------------------------------
    if not tracks:

        return (
            [],
            set(),
            set(range(len(observations)))
        )

    if not observations:

        return (
            [],
            set(range(len(tracks))),
            set()
        )

    # -----------------------------------------------------
    # Stage 1
    # Global assignment
    # -----------------------------------------------------
    (
        matches,
        unmatched_tracks,
        unmatched_observations
    ) = assign_tracks(
        observations=observations,
        tracks=tracks,
        config=config
    )

    return (
        matches,
        unmatched_tracks,
        unmatched_observations
    )