import pytest
from engine.bandit import VortexBanditRouter


def test_bandit_prefers_healthy_gateway():
    router = VortexBanditRouter()
    router.register_gateway("BANK_A", mdr_percent=1.0)
    router.register_gateway("BANK_B", mdr_percent=1.0)

    # Simulate BANK_A having heavy failures
    for _ in range(50):
        router.feedback("BANK_A", latency_ms=800.0, success=False)
        router.feedback("BANK_B", latency_ms=120.0, success=True)

    # In 100 queries, BANK_B should receive the overwhelming majority
    selections = [router.select_gateway() for _ in range(100)]
    assert selections.count("BANK_B") > 85


def test_telemetry_window_metrics():
    router = VortexBanditRouter()
    router.register_gateway("BANK_A", mdr_percent=1.0)

    router.feedback("BANK_A", latency_ms=100.0, success=True)
    router.feedback("BANK_A", latency_ms=200.0, success=True)

    metrics = router.get_all_metrics()["BANK_A"]
    assert metrics["count"] == 2
    assert metrics["success_rate"] == 1.0
    assert metrics["p50_ms"] == 150.0