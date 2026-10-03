import random
import time
import numpy as np
from typing import Dict, List, Optional

# Compatible import supporting either TelemetryWindow or SlidingWindowTelemetry
try:
    from engine.telemetry import TelemetryWindow as TelemetryTracker
except ImportError:
    from engine.telemetry import SlidingWindowTelemetry as TelemetryTracker


class GatewayArm:
    """Represents an acquiring bank gateway with exponentially decaying Beta priors."""

    def __init__(self, name: str, base_mdr: float = 0.012, decay_factor: float = 0.98):
        self.name = name
        self.gateway_id = name
        self.base_mdr = base_mdr
        self.mdr_percent = base_mdr * 100.0 if base_mdr < 1.0 else base_mdr
        self.decay_factor = decay_factor

        # Prior distribution parameters: Beta(alpha, beta)
        self.alpha: float = 8.0
        self.beta: float = 1.0
        self.telemetry = TelemetryTracker(window_seconds=30.0)
        self.last_update: float = time.time()

    def decay_priors(self) -> None:
        """Applies exponential recency decay to adapt rapidly to bank CBS brownouts & recovery."""
        now = time.time()
        elapsed = now - self.last_update
        if elapsed > 0.5:
            multiplier = self.decay_factor ** min(elapsed, 10.0)
            self.alpha = 1.0 + (self.alpha - 1.0) * multiplier
            self.beta = 1.0 + (self.beta - 1.0) * multiplier
            self.last_update = now

    def sample_success_probability(self) -> float:
        self.decay_priors()
        return float(np.random.beta(max(self.alpha, 0.01), max(self.beta, 0.01)))

    # Alias for sample_success_probability
    def sample_success_prob(self) -> float:
        return self.sample_success_probability()

    def update(self, success: bool, latency_ms: float, cost_mdr: Optional[float] = None, state: str = "SUCCESS") -> None:
        # Pass metrics into sliding window telemetry
        if hasattr(self.telemetry, "record"):
            try:
                self.telemetry.record(latency_ms=latency_ms, success=success)
            except TypeError:
                self.telemetry.record(success=success, latency_ms=latency_ms, cost_mdr=cost_mdr or self.base_mdr, state=state)

        # Decay priors and increment based on transaction outcome
        self.alpha = 1.0 + self.decay_factor * (self.alpha - 1.0)
        self.beta = 1.0 + self.decay_factor * (self.beta - 1.0)

        if success:
            self.alpha += 1.0
        else:
            self.beta += 1.4  # Slightly stronger penalty for CBS drop/timeouts
        self.last_update = time.time()


class VortexRouter:
    """Multi-Objective Contextual Bandit Payment Gateway Router."""

    def __init__(
        self,
        strategy: str = "thompson_sampling",
        latency_budget_ms: float = 1000.0,
        latency_sla_ms: Optional[float] = None,
        w_success: float = 1.0,
        w_latency: float = 0.35,
        w_cost: float = 0.20,
        latency_weight: Optional[float] = None,
        fee_weight: Optional[float] = None,
    ):
        self.strategy = strategy
        self.latency_budget_ms = latency_sla_ms or latency_budget_ms
        self.w_success = w_success
        self.w_latency = latency_weight if latency_weight is not None else w_latency
        self.w_cost = fee_weight if fee_weight is not None else w_cost
        self.arms: Dict[str, GatewayArm] = {}

    def register_gateway(self, name: str, base_mdr: float = 0.012, mdr_percent: Optional[float] = None) -> None:
        fee = (mdr_percent / 100.0) if mdr_percent is not None else base_mdr
        self.arms[name] = GatewayArm(name=name, base_mdr=fee)

    def _get_arm_p95(self, arm: GatewayArm) -> float:
        """Extracts P95 latency from telemetry metrics dictionary safely."""
        metrics = arm.telemetry.get_metrics() if hasattr(arm.telemetry, "get_metrics") else arm.telemetry.compute_stats()
        return metrics.get("p95_ms", metrics.get("p95_latency_ms", 120.0))

    def _calculate_utility(self, arm: GatewayArm, sampled_p_success: float) -> float:
        p95 = self._get_arm_p95(arm)
        latency_penalty = min(p95 / self.latency_budget_ms, 2.5)
        cost_penalty = arm.base_mdr / 0.03  # Normalized relative to 3.0% aggregator benchmark
        return (self.w_success * sampled_p_success) - (self.w_latency * latency_penalty) - (self.w_cost * cost_penalty)

    def select_gateway(self) -> str:
        if not self.arms:
            raise RuntimeError("No gateway arms registered in VortexRouter.")

        best_arm: Optional[str] = None
        best_score = -float("inf")

        for name, arm in self.arms.items():
            sampled_success = arm.sample_success_probability()
            utility = self._calculate_utility(arm, sampled_success)
            if utility > best_score:
                best_score = utility
                best_arm = name

        return best_arm or list(self.arms.keys())[0]

    def feedback(self, gateway_id: str, success_or_latency, latency_or_success, cost_mdr: float = 0.012, state: str = "SUCCESS") -> None:
        """Polymorphic feedback method accepting either (gw, success, lat) or (gw, lat, success)."""
        if gateway_id not in self.arms:
            return

        if isinstance(success_or_latency, bool):
            success = success_or_latency
            latency = float(latency_or_success)
        else:
            latency = float(success_or_latency)
            success = bool(latency_or_success)

        self.arms[gateway_id].update(success=success, latency_ms=latency, cost_mdr=cost_mdr, state=state)

    def get_all_metrics(self) -> Dict[str, dict]:
        report = {}
        for gid, arm in self.arms.items():
            stats = arm.telemetry.get_metrics() if hasattr(arm.telemetry, "get_metrics") else arm.telemetry.compute_stats()
            report[gid] = {
                **stats,
                "alpha": round(arm.alpha, 2),
                "beta": round(arm.beta, 2),
                "mdr_percent": round(arm.base_mdr * 100, 2),
            }
        return report


# Dual alias so both VortexRouter and VortexBanditRouter imports succeed everywhere
VortexBanditRouter = VortexRouter
