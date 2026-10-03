import random
import time
from typing import Tuple

class MockBankGateway:
    def __init__(self, name: str, base_latency_ms: float = 120.0, base_success_rate: float = 0.99, mdr_rate: float = 0.012, timeout_threshold_ms: float = 1100.0, failure_rate: float = 0.01):
        self.name = name
        self.base_latency_ms = base_latency_ms
        self.base_success_rate = base_success_rate if base_success_rate != 0.99 or failure_rate == 0.01 else (1.0 - failure_rate)
        self.mdr_rate = mdr_rate
        self.timeout_threshold_ms = timeout_threshold_ms
        self.degraded = False
        self.degraded_latency_ms = 1350.0
        self.degraded_success_rate = 0.55

    def set_degraded(self, is_degraded: bool, latency: float = 1350.0, success_rate: float = 0.55):
        self.degraded = is_degraded
        self.degraded_latency_ms = latency
        self.degraded_success_rate = success_rate

    def trigger_brownout(self, latency_multiplier: float = 8.0, failure_rate: float = 0.45):
        self.set_degraded(True, latency=self.base_latency_ms * latency_multiplier, success_rate=1.0 - failure_rate)

    def recover(self, original_latency_ms: float = 120.0, original_failure_rate: float = 0.01):
        self.set_degraded(False)

    def execute_payment(self, amount: float = 1000.0) -> Tuple[str, bool, float, float]:
        mean_latency = self.degraded_latency_ms if self.degraded else self.base_latency_ms
        success_chance = self.degraded_success_rate if self.degraded else self.base_success_rate
        actual_latency = max(25.0, random.gauss(mean_latency, mean_latency * 0.12))
        cost = amount * self.mdr_rate

        if actual_latency >= self.timeout_threshold_ms:
            return "TIMEOUT_PENDING", False, actual_latency, cost
        if random.random() <= success_chance:
            return "SUCCESS", True, actual_latency, cost
        return "FAILED", False, actual_latency, cost
