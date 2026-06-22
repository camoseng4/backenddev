from typing import Tuple

from track.models import RuntimeTrack
from track.contracts import TrackerConfig


# ---------------------------------------------------------
# CLIP VELOCITY
# ---------------------------------------------------------
def clip_velocity(
    velocity: Tuple[float, float],
    max_speed: float
) -> Tuple[float, float]:

    vx, vy = velocity

    vx = max(
        -max_speed,
        min(max_speed, vx)
    )

    vy = max(
        -max_speed,
        min(max_speed, vy)
    )

    return (
        vx,
        vy
    )


# ---------------------------------------------------------
# VELOCITY MAGNITUDE
# ---------------------------------------------------------
def velocity_magnitude(
    velocity: Tuple[float, float]
) -> float:

    vx, vy = velocity

    return (
        vx * vx +
        vy * vy
    ) ** 0.5


# ---------------------------------------------------------
# PREDICTION VELOCITY WEIGHT
# ---------------------------------------------------------
def prediction_velocity_weight(
    track: RuntimeTrack,
    config: TrackerConfig
) -> float:
    """
    Young tracks trust velocity less.

    Missing tracks trust velocity less.

    Mature continuously-observed tracks
    trust velocity most.
    """

    if track.hit_count < config.min_confirm_hits:
        base_weight = 0.25
    else:
        base_weight = 1.0

    miss_decay = (
        config.miss_decay_factor
        ** track.consecutive_misses
    )

    return base_weight * miss_decay


# ---------------------------------------------------------
# PREDICT POSITION
# ---------------------------------------------------------
def predict_position(
    track: RuntimeTrack,
    current_timestamp: float,
    config: TrackerConfig
) -> Tuple[float, float]:
    """
    Constant velocity prediction.

    Conservative by design.
    """

    px, py = track.current_position

    vx, vy = track.velocity

    dt = max(
        current_timestamp -
        track.last_seen_timestamp,
        0.0
    )

    velocity_weight = prediction_velocity_weight(
        track,
        config
    )

    predicted_x = (
        px +
        vx * dt * velocity_weight
    )

    predicted_y = (
        py +
        vy * dt * velocity_weight
    )

    return (
        predicted_x,
        predicted_y
    )


# ---------------------------------------------------------
# UPDATE STORED PREDICTION
# ---------------------------------------------------------
def update_prediction(
    track: RuntimeTrack,
    current_timestamp: float,
    config: TrackerConfig
) -> None:

    track.predicted_position = predict_position(
        track=track,
        current_timestamp=current_timestamp,
        config=config
    )

    track.last_prediction_timestamp = (
        current_timestamp
    )


# ---------------------------------------------------------
# MEASURE VELOCITY
# ---------------------------------------------------------
def measure_velocity(
    old_position: Tuple[float, float],
    new_position: Tuple[float, float],
    dt: float
) -> Tuple[float, float]:

    if dt <= 1e-6:
        return (
            0.0,
            0.0
        )

    vx = (
        new_position[0] -
        old_position[0]
    ) / dt

    vy = (
        new_position[1] -
        old_position[1]
    ) / dt

    return (
        vx,
        vy
    )


# ---------------------------------------------------------
# SMOOTH VELOCITY
# ---------------------------------------------------------
def smooth_velocity(
    old_velocity: Tuple[float, float],
    measured_velocity: Tuple[float, float],
    smoothing_factor: float
) -> Tuple[float, float]:

    old_vx, old_vy = old_velocity

    measured_vx, measured_vy = measured_velocity

    vx = (
        smoothing_factor * old_vx
        +
        (1.0 - smoothing_factor)
        * measured_vx
    )

    vy = (
        smoothing_factor * old_vy
        +
        (1.0 - smoothing_factor)
        * measured_vy
    )

    return (
        vx,
        vy
    )


# ---------------------------------------------------------
# UPDATE MOTION STATE
# ---------------------------------------------------------
def update_motion_state(
    track: RuntimeTrack,
    new_position: Tuple[float, float],
    current_timestamp: float,
    config: TrackerConfig
) -> None:
    """
    Motion update after successful assignment.
    """

    dt = max(
        current_timestamp -
        track.last_seen_timestamp,
        1e-6
    )

    measured_velocity = measure_velocity(
        old_position=track.current_position,
        new_position=new_position,
        dt=dt
    )

    smoothed_velocity = smooth_velocity(
        old_velocity=track.velocity,
        measured_velocity=measured_velocity,
        smoothing_factor=config.velocity_smoothing
    )

    smoothed_velocity = clip_velocity(
        smoothed_velocity,
        config.max_speed_pixels_per_second
    )

    track.velocity = smoothed_velocity

    track.speed_pixels_per_second = (
        velocity_magnitude(
            smoothed_velocity
        )
    )

    track.current_position = new_position

    track.predicted_position = None

    track.last_prediction_timestamp = (
        current_timestamp
    )