"""Bias-labeled gyro orientation integration; no drift-free heading or position claim."""
from bisect import bisect_left
import numpy as np
from scipy.spatial.transform import Rotation


def initial_stationary_window(samples, duration_s=.75):
    if not samples:
        raise ValueError("No IMU samples")
    start = int(samples[0]["timestamp_ns"])
    window = [sample for sample in samples if 0 <= int(sample["timestamp_ns"]) - start <= duration_s * 1e9]
    if len(window) < 20 or (int(window[-1]["timestamp_ns"]) - start) / 1e9 < duration_s * .9:
        return {"accepted": False, "reason": "insufficient samples/time span in stationary window"}
    gyro = np.array([sample["angular_velocity"] for sample in window], float)
    acceleration = np.array([sample["acceleration"] for sample in window], float)
    mean_acceleration = acceleration.mean(axis=0)
    plausible = np.linalg.norm(gyro.std(axis=0)) < .02 and np.linalg.norm(gyro.mean(axis=0)) < .2 and abs(np.linalg.norm(mean_acceleration) - 9.81) < .8 and np.linalg.norm(acceleration.std(axis=0)) < .5
    return {"accepted": bool(plausible), "assumption": "initial window is stationary; IMU alone does not prove this", "samples": len(window), "duration_s": (int(window[-1]["timestamp_ns"]) - start) / 1e9,
            "gyro_bias_rad_s": gyro.mean(axis=0).tolist() if plausible else None, "mean_specific_force_m_s2": mean_acceleration.tolist(), "reason": "numerical stationary criteria met" if plausible else "initial window fails stationary criteria"}


def find_initial_quiet_window(samples, search_s=5, duration_s=.75):
    """Offline calibration search: report the selected quiet interval, without using ground truth."""
    if not samples:
        raise ValueError("No IMU samples")
    origin = int(samples[0]["timestamp_ns"])
    for start in np.arange(0, max(0, search_s - duration_s) + 1e-9, .25):
        candidate = [sample for sample in samples if int(sample["timestamp_ns"]) >= origin + round(start * 1e9)]
        if not candidate:
            break
        result = initial_stationary_window(candidate, duration_s)
        if result["accepted"]:
            result.update(start_offset_s=float(start), end_offset_s=float(start + result["duration_s"]), selection="first quiet interval in initial search; offline and assumed stationary, not GT-calibrated")
            return result
    return {"accepted": False, "gyro_bias_rad_s": None, "reason": "no qualifying initial quiet window", "search_s": search_s}


def integrate_gyro(samples, bias=(0, 0, 0), max_gap_s=.1, initial_rotation=None):
    bias = np.asarray(bias, float)
    if bias.shape != (3,) or not np.isfinite(bias).all() or max_gap_s <= 0:
        raise ValueError("Invalid gyro bias or gap limit")
    rotation = initial_rotation if initial_rotation is not None else Rotation.identity()
    output = []; previous = None; continuous = True; gaps = 0
    for sample in samples:
        timestamp = int(sample["timestamp_ns"]); rate = np.asarray(sample["angular_velocity"], float)
        if rate.shape != (3,) or not np.isfinite(rate).all():
            raise ValueError("Gyro samples must contain finite xyz rad/s")
        if previous is not None:
            dt = (timestamp - previous[0]) / 1e9
            if dt <= 0:
                raise ValueError("IMU timestamps must strictly increase")
            if dt > max_gap_s:
                continuous = False; gaps += 1
            else:
                midpoint = (rate + previous[1]) / 2 - bias
                rotation = rotation * Rotation.from_rotvec(midpoint * dt)
        quat = rotation.as_quat()
        output.append({"timestamp_ns": str(timestamp), "quaternion_xyzw": quat.tolist(), "rotation": rotation, "continuous": continuous, "gaps_seen": gaps})
        previous = (timestamp, rate)
    return output


def nearest_orientation(orientations, timestamps, target_ns, max_gap_ns=10000000):
    index = bisect_left(timestamps, target_ns)
    candidates = [i for i in (index - 1, index) if 0 <= i < len(timestamps)]
    if not candidates:
        return None
    best = min(candidates, key=lambda i: abs(timestamps[i] - target_ns))
    return orientations[best] if abs(timestamps[best] - target_ns) <= max_gap_ns else None


def blend_rotation(gyro_delta, visual_delta, gain=.2, gate_degrees=8):
    """Geodesic attitude-only complementary update; not a complete VIO estimator."""
    if not 0 <= gain <= 1 or gate_degrees <= 0:
        raise ValueError("Invalid rotation fusion settings")
    residual = (gyro_delta.inv() * visual_delta).as_rotvec()
    disagreement = float(np.linalg.norm(residual) * 180 / np.pi)
    if disagreement > gate_degrees:
        return gyro_delta, {"visual_used": False, "reason": "rotation disagreement gate", "disagreement_deg": disagreement}
    return gyro_delta * Rotation.from_rotvec(gain * residual), {"visual_used": True, "disagreement_deg": disagreement, "gain": gain}
