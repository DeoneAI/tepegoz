"""Linear Kalman filters; covariance updates use the Joseph form."""
import math
import numpy as np


class LinearKalmanFilter:
    def __init__(self, state, covariance):
        self.x = np.asarray(state, dtype=np.float64).reshape(-1)
        self.P = np.asarray(covariance, dtype=np.float64).copy()
        if self.P.shape != (self.x.size, self.x.size) or not np.isfinite(self.P).all() or not np.isfinite(self.x).all():
            raise ValueError("Invalid state/covariance")

    def predict(self, F, Q, control=None):
        F, Q = np.asarray(F, float), np.asarray(Q, float)
        self.x = F @ self.x
        if control is not None:
            self.x += np.asarray(control, float)
        self.P = F @ self.P @ F.T + Q
        self.P = (self.P + self.P.T) / 2
        return self.x.copy()

    def update(self, measurement, H, R, gate=None):
        z, H, R = np.asarray(measurement, float), np.asarray(H, float), np.asarray(R, float)
        if not np.isfinite(z).all():
            raise ValueError("Measurements must be finite")
        innovation = z - H @ self.x
        S = H @ self.P @ H.T + R
        distance = float(innovation @ np.linalg.solve(S, innovation))
        if gate is not None and distance > gate:
            return {"accepted": False, "mahalanobis_squared": distance}
        gain = np.linalg.solve(S, H @ self.P).T
        self.x += gain @ innovation
        residual = np.eye(self.x.size) - gain @ H
        self.P = residual @ self.P @ residual.T + gain @ R @ gain.T
        self.P = (self.P + self.P.T) / 2
        return {"accepted": True, "mahalanobis_squared": distance}


class ScalarKalmanFilter(LinearKalmanFilter):
    def __init__(self, value=10, variance=4):
        if not math.isfinite(variance) or variance < 0:
            raise ValueError("Variance must be nonnegative")
        super().__init__([value], [[variance]])

    def step(self, measurement, process_variance=1, measurement_variance=9):
        if process_variance < 0 or measurement_variance <= 0:
            raise ValueError("Q must be nonnegative and R positive")
        self.predict([[1]], [[process_variance]])
        if measurement is not None:
            return self.update([measurement], [[1]], [[measurement_variance]])
        return {"accepted": False, "missing": True}


class ConstantVelocity2D(LinearKalmanFilter):
    """State [px, py, vx, vy], continuous coordinates and seconds; no frame conversion."""
    def __init__(self, position=(0, 0), velocity=(0, 0), acceleration_variance=1, measurement_variance=1):
        super().__init__([*position, *velocity], np.diag([10., 10., 25., 25.]))
        if acceleration_variance < 0 or measurement_variance <= 0:
            raise ValueError("Invalid noise variance")
        self.acceleration_variance = acceleration_variance
        self.R = np.eye(2) * measurement_variance
        self.H = np.eye(2, 4)

    def advance(self, dt, measurement=None, gate=9.21):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be positive seconds")
        F = np.eye(4); F[0, 2] = F[1, 3] = dt
        G = np.array([[dt * dt / 2, 0], [0, dt * dt / 2], [dt, 0], [0, dt]])
        self.predict(F, self.acceleration_variance * G @ G.T)
        return self.update(measurement, self.H, self.R, gate) if measurement is not None else {"accepted": False, "missing": True}


def heading_motion_and_jacobian(state, dt):
    """Heading-aware state [x,y,heading,speed], radians; EKF study model."""
    x, y, theta, speed = np.asarray(state, float)
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be positive seconds")
    predicted = np.array([x + speed * math.cos(theta) * dt, y + speed * math.sin(theta) * dt, (theta + math.pi) % (2 * math.pi) - math.pi, speed])
    F = np.eye(4)
    F[0, 2], F[1, 2] = -speed * math.sin(theta) * dt, speed * math.cos(theta) * dt
    F[0, 3], F[1, 3] = math.cos(theta) * dt, math.sin(theta) * dt
    return predicted, F
