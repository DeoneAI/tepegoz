"""Reproducible Week 3 Kalman exercises and plots; synthetic learning evidence only."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from localization.filters import ScalarKalmanFilter, ConstantVelocity2D, heading_motion_and_jacobian


def scalar_series(output, plt):
    """Scalar random-walk model versus noisy/missing position observations, fixed seed."""
    rng = np.random.default_rng(42)
    times = np.arange(240) * .1
    truth = 10 + 1.5 * np.sin(.6 * times) + 3 * (times >= 12)
    observations = truth + rng.normal(0, 1.5, len(times))
    missing = (np.arange(len(times)) % 17 == 8) | ((times >= 8) & (times < 9))
    observations[missing] = np.nan
    estimated, variances, metrics = {}, {}, []
    visible = np.isfinite(observations)
    for r in (.25, 2.25, 25.):
        filter = ScalarKalmanFilter(10, 4)
        states, covariance = [], []
        for measurement in observations:
            filter.step(float(measurement) if np.isfinite(measurement) else None, .08, r)
            states.append(float(filter.x[0])); covariance.append(float(filter.P[0, 0]))
        estimated[r], variances[r] = np.array(states), np.array(covariance)
        metrics.append({"R": r, "Q_per_step": .08, "position_rmse_all_times": float(np.sqrt(np.mean((estimated[r] - truth) ** 2))),
                        "position_rmse_observed_times": float(np.sqrt(np.mean((estimated[r][visible] - truth[visible]) ** 2)))})
    raw_rmse = float(np.sqrt(np.mean((observations[visible] - truth[visible]) ** 2)))
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True, layout="constrained")
    axes[0].plot(times, truth, color="black", linewidth=1.5, label="synthetic truth")
    axes[0].scatter(times, observations, color="gray", s=9, alpha=.45, label="noisy observations; gaps are missing")
    for r in estimated:
        axes[0].plot(times, estimated[r], linewidth=.9, label=f"scalar KF R={r}")
        axes[1].plot(times, np.abs(estimated[r] - truth), linewidth=.9, label=f"R={r}")
    error = estimated[2.25] - truth; sigma = np.sqrt(variances[2.25])
    axes[2].plot(times, error, label="signed error, R=2.25")
    axes[2].fill_between(times, -2 * sigma, 2 * sigma, alpha=.2, label="±2 model sigma; not calibrated coverage")
    axes[0].set(ylabel="Position (m)", title="Noisy measurements and a scalar predict/update sequence")
    axes[1].set(ylabel="Absolute error (m)", title="Higher R smooths more but delays changes")
    axes[2].set(ylabel="Error (m)", xlabel="Time (s)", title="Missing observations increase model uncertainty; the step violates the random-walk prior")
    for ax in axes:
        ax.axvspan(8, 9, color="gray", alpha=.12, label="one-second observation gap")
        ax.legend(fontsize=8, ncols=3); ax.grid(alpha=.2)
    fig.suptitle("SYNTHETIC 1D Kalman experiment: identical observations, three measurement variances")
    fig.savefig(output / "scalar-timeseries.svg"); fig.savefig(output / "scalar-timeseries.png", dpi=150); plt.close(fig)
    with (output / "scalar-timeseries.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time_s", "truth_m", "observation_m", *[f"estimate_R_{r}" for r in estimated], *[f"variance_R_{r}" for r in estimated]])
        for i, time in enumerate(times):
            writer.writerow([time, truth[i], observations[i] if visible[i] else "", *[values[i] for values in estimated.values()], *[values[i] for values in variances.values()]])
    return {"seed": 42, "samples": len(times), "dt_s": .1, "missing_observations": int(missing.sum()), "raw_rmse_observed_times": raw_rmse,
            "variants": metrics, "model": "scalar position random walk, F=H=1; unmodeled position step at 12 s", "evidence_type": "synthetic, not phone or vehicle measurements"}


def simulate(turning, q, r, seed=42):
    rng = np.random.default_rng(seed)
    dt = rng.uniform(.06, .16, 240); times = np.cumsum(dt)
    theta = .7 * np.sin(times * .22) if turning else np.full(len(times), .25)
    velocity = np.c_[np.cos(theta), np.sin(theta)] * 3
    truth = np.cumsum(velocity * dt[:, None], axis=0)
    measurements = truth + rng.normal(0, 1.5, truth.shape)
    missing = rng.random(len(dt)) < .18
    missing[0] = False
    measurements[missing] = np.nan
    measurements[60] += [25, -25]
    filter = ConstantVelocity2D(position=(0, 0), acceleration_variance=q, measurement_variance=r)
    states, covariance, accepted = [], [], []
    for interval, observation in zip(dt, measurements):
        result = filter.advance(float(interval), observation if np.isfinite(observation).all() else None)
        states.append(filter.x.copy()); covariance.append(filter.P.copy()); accepted.append(result["accepted"])
    states, covariance = np.array(states), np.array(covariance)
    position_error = states[:, :2] - truth
    visible = np.isfinite(measurements).all(axis=1)
    metrics = {"position_rmse": float(np.sqrt(np.mean(np.sum(position_error ** 2, axis=1)))),
               "raw_position_rmse_observed_only": float(np.sqrt(np.mean(np.sum((measurements[visible] - truth[visible]) ** 2, axis=1)))),
               "missing_measurements": int(missing.sum()), "rejected_present_measurements": int(visible.sum() - sum(accepted)),
               "q_acceleration_variance": q, "r_position_variance": r, "turning": turning, "seed": seed}
    return times, truth, measurements, states, covariance, metrics


def run(output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    series = scalar_series(output, plt)
    scalar = []
    for r in (1, 9, 100):
        filter = ScalarKalmanFilter(10, 4); filter.step(14, 1, r)
        scalar.append({"R": r, "prior_x": 10, "prior_variance": 5, "measurement": 14, "K": 5 / (5 + r), "posterior_x": float(filter.x[0]), "posterior_variance": float(filter.P[0, 0])})
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.errorbar([row["R"] for row in scalar], [row["posterior_x"] for row in scalar], yerr=[math.sqrt(row["posterior_variance"]) for row in scalar], fmt="o", capsize=5, label="posterior ±1 model sigma")
    ax.axhline(10, color="gray", linestyle="--", label="prediction 10 m"); ax.axhline(14, color="orange", linestyle="--", label="measurement 14 m")
    ax.set(xscale="log", xlabel="Measurement variance R (m²)", ylabel="Estimated position (m)", title="Scalar KF exercise: x=10, P=4, Q=1, z=14"); ax.legend(); fig.tight_layout()
    fig.savefig(output / "scalar-kf.svg"); fig.savefig(output / "scalar-kf.png", dpi=150); plt.close(fig)
    metrics = []
    for turning in (False, True):
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        for q in (.1, 1., 10.):
            times, truth, observations, states, covariance, result = simulate(turning, q, 2.25)
            metrics.append(result)
            axes[0, 0].plot(states[:, 0], states[:, 1], label=f"Q scale {q}")
            axes[0, 1].plot(times, np.linalg.norm(states[:, :2] - truth, axis=1), label=f"Q scale {q}")
            axes[1, 1].plot(times, np.sqrt(covariance[:, 0, 0]), label=f"Q scale {q}")
            if q == 1:
                axes[0, 0].scatter(observations[:, 0], observations[:, 1], s=4, color="gray", alpha=.35, label="noisy/missed observations")
                axes[0, 0].plot(truth[:, 0], truth[:, 1], "k--", label="synthetic ground truth")
                error = states[:, 0] - truth[:, 0]; sigma = np.sqrt(covariance[:, 0, 0])
                axes[1, 0].plot(times, error, label="x error, Q=1")
                axes[1, 0].fill_between(times, -2 * sigma, 2 * sigma, alpha=.2, label="±2 model sigma; not calibrated coverage")
        axes[0, 0].set(title="Trajectory", xlabel="x (m)", ylabel="y (m)"); axes[0, 0].axis("equal")
        axes[0, 1].set(title="Position error", xlabel="Time (s)", ylabel="Euclidean error (m)")
        axes[1, 0].set(title="Error and covariance envelope", xlabel="Time (s)", ylabel="x error (m)")
        axes[1, 1].set(title="Position uncertainty response", xlabel="Time (s)", ylabel="sqrt(Pxx) (m)")
        for ax in axes.flat:
            ax.legend(fontsize=7); ax.grid(alpha=.2)
        name = "turning" if turning else "straight"
        fig.suptitle(f"SYNTHETIC constant-velocity KF study: {name}, variable dt, missing data and an outlier")
        fig.tight_layout(); fig.savefig(output / f"kf-{name}.svg"); fig.savefig(output / f"kf-{name}.png", dpi=150); plt.close(fig)
    state, jacobian = heading_motion_and_jacobian([0, 0, .4, 5], .1)
    report = {"evidence_type": "synthetic learning exercises; not phone acquisition or vehicle validation", "scalar_examples": scalar, "scalar_timeseries": series, "kinematic_experiments": metrics,
              "yaw_bias_exercise": {"measured_rad_s": .11, "bias_rad_s": .01, "duration_s": 10, "uncorrected_rad": 1.1, "corrected_rad": 1., "uncorrected_deg": math.degrees(1.1), "corrected_deg": math.degrees(1.)},
              "heading_ekf_example": {"state": [0, 0, .4, 5], "dt": .1, "predicted": state.tolist(), "F": jacobian.tolist()},
              "assumptions": ["CV state [px,py,vx,vy] with position observations", "Discrete white acceleration Q=variance*G*G^T with dt-specific G", "Joseph covariance; 2D innovation gate 9.21", "This is neither VIO nor SLAM; turning violates constant-velocity assumptions"]}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return {"output": str(output.resolve()), "scalar_examples": scalar, "experiments": len(metrics)}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument("--output", default=".tools/experiments/estimation-lab")
    try:
        print(json.dumps(run(cli.parse_args().output)))
    except (OSError, ValueError, ImportError) as error:
        cli.exit(1, f"{error}\n")
