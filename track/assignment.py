from typing import List, Tuple, Set

import numpy as np
from scipy.optimize import linear_sum_assignment

from track.models import RuntimeTrack
from track.scorer import (
    match_cost,
    IMPOSSIBLE_COST
)


# ---------------------------------------------------------
# BUILD COST MATRIX
# ---------------------------------------------------------
def build_cost_matrix(
    observations: List[dict],
    tracks: List[RuntimeTrack],
    config
) -> np.ndarray:
    """
    Build pairwise assignment cost matrix.

    Lower cost is better.

    Impossible pairs receive IMPOSSIBLE_COST and
    are effectively excluded from assignment.
    """

    num_tracks = len(tracks)
    num_observations = len(observations)

    if num_tracks == 0 or num_observations == 0:

        return np.zeros(
            (num_tracks, num_observations),
            dtype=np.float32
        )

    matrix = np.zeros(
        (num_tracks, num_observations),
        dtype=np.float32
    )

    for ti, track in enumerate(tracks):

        for oi, obs in enumerate(observations):

            matrix[ti, oi] = match_cost(
                track=track,
                obs=obs,
                config=config
            )

    return matrix


# ---------------------------------------------------------
# ASSIGN TRACKS
# ---------------------------------------------------------
def assign_tracks(
    observations: List[dict],
    tracks: List[RuntimeTrack],
    config
) -> Tuple[
    List[Tuple[int, int]],
    Set[int],
    Set[int]
]:
    """
    Global optimal assignment.

    Returns:

        matches:
            [(track_index, observation_index)]

        unmatched_tracks:
            set[int]

        unmatched_observations:
            set[int]
    """

    num_tracks = len(tracks)
    num_observations = len(observations)

    # -----------------------------------------------------
    # EMPTY CASES
    # -----------------------------------------------------
    if num_tracks == 0:

        return (
            [],
            set(),
            set(range(num_observations))
        )

    if num_observations == 0:

        return (
            [],
            set(range(num_tracks)),
            set()
        )

    # -----------------------------------------------------
    # BUILD COST MATRIX
    # -----------------------------------------------------
    cost_matrix = build_cost_matrix(
        observations=observations,
        tracks=tracks,
        config=config
    )

    # -----------------------------------------------------
    # HUNGARIAN ASSIGNMENT
    # -----------------------------------------------------
    row_indices, col_indices = (
        linear_sum_assignment(
            cost_matrix
        )
    )

    matches = []

    matched_tracks = set()
    matched_observations = set()

    # -----------------------------------------------------
    # ACCEPT VALID MATCHES ONLY
    # -----------------------------------------------------
    for track_index, observation_index in zip(
        row_indices,
        col_indices
    ):

        cost = cost_matrix[
            track_index,
            observation_index
        ]

        # impossible pair
        if cost >= IMPOSSIBLE_COST:
            continue

        # configurable acceptance threshold
        if cost > config.match_cost_threshold:
            continue

        matches.append(
            (
                track_index,
                observation_index
            )
        )

        matched_tracks.add(
            track_index
        )

        matched_observations.add(
            observation_index
        )

    # -----------------------------------------------------
    # UNMATCHED
    # -----------------------------------------------------
    unmatched_tracks = (
        set(range(num_tracks))
        - matched_tracks
    )

    unmatched_observations = (
        set(range(num_observations))
        - matched_observations
    )

    return (
        matches,
        unmatched_tracks,
        unmatched_observations
    )