from dataclasses import dataclass


# =========================================================
# TRACKER CONFIG (SINGLE SOURCE OF TRUTH)
# =========================================================
@dataclass(frozen=True)
class TrackerConfig:
    """
    Minimal working config aligned with predictor + matcher + engine.
    """

    # -----------------------------
    # lifecycle
    # -----------------------------
    min_confirm_hits: int = 2

    max_inactive_seconds: float = 5
    max_misses: int = 5

    base_motion_gate_px = 100
    velocity_gate_scale = 0.7
    max_motion_gate_px = 250

    # -----------------------------
    # motion
    # -----------------------------
    velocity_smoothing: float = 0.8
    max_speed_pixels_per_second: float = 400.0

    # IMPORTANT: missing in your error chain
    miss_decay_factor: float = 0.85

    # -----------------------------
    # matching
    # -----------------------------
    match_threshold: float = 0.30

    # -----------------------------
    # spatial scoring
    # -----------------------------
    max_distance: float = 100.0
    spatial_alpha: float = 4.0

    # -----------------------------
    # appearance
    # -----------------------------
    embedding_weight: float = 0.10
    spatial_weight: float = 0.90


        # lifecycle
    min_confirm_hits: int = 2
    max_inactive_seconds: float = 1.5
    max_misses: int = 5

    # ADD THIS (fix current crash)
    max_tentative_seconds: float = 1.0

    # motion
    velocity_smoothing: float = 0.8
    max_speed_pixels_per_second: float = 400.0
    miss_decay_factor: float = 0.85

    # matching
    match_threshold: float = 0.30

    # spatial
    max_distance: float = 100.0
    spatial_alpha: float = 4.0

    # -----------------------------
# MOTION GATING
# -----------------------------
    #base_motion_gate_px: float = 40.0
    #velocity_gate_scale: float = 0.25
    #max_motion_gate_px: float = 120.0
    lost_gate_multiplier: float = 1.2

# uncertainty (USED BY scorer gating)
    velocity_uncertainty_px_per_second: float = 30.0


    # -----------------------------
# SCORING WEIGHTS
# -----------------------------
    spatial_weight: float = 0.70
    velocity_weight: float = 0.20
    appearance_weight: float = 0.10

    # optional but often referenced
    lost_age_penalty_weight: float = 0.05
    match_cost_threshold: float = 0.30
    young_track_hits: int = 3
    max_active_gap_seconds: float = 1.0