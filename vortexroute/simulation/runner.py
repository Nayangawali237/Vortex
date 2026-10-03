import asyncio
import uuid
from engine.bandit import VortexBanditRouter
from gateways.mock_gateways import MockBankGateway


async def run_benchmark(total_txns: int = 1500):
    router = VortexBanditRouter()
    gateways = {
        "HDFC": MockBankGateway("HDFC", base_latency_ms=100.0, failure_rate=0.01),
        "ICICI": MockBankGateway("ICICI", base_latency_ms=110.0, failure_rate=0.02),
        "AXIS": MockBankGateway("AXIS", base_latency_ms=120.0, failure_rate=0.02),
    }

    router.register_gateway("HDFC", mdr_percent=1.2)
    router.register_gateway("ICICI", mdr_percent=1.1)
    router.register_gateway("AXIS", mdr_percent=1.0)

    print(f"[*] Starting benchmark simulation with {total_txns} transactions...")

    routes_count = {"HDFC": 0, "ICICI": 0, "AXIS": 0}
    successes = 0

    for i in range(total_txns):
        # Induce a brownout on primary bank at transaction #300
        if i == 300:
            print("\n[!] INJECTING BROWNOUT on HDFC (latency -> 900ms, fail_rate -> 40%)...")
            gateways["HDFC"].trigger_brownout(latency_multiplier=9.0, failure_rate=0.40)

        # Recover primary bank at transaction #1000
        if i == 1000:
            print("\n[+] RECOVERING HDFC back to normal performance...")
            gateways["HDFC"].recover(original_latency_ms=100.0, original_failure_rate=0.01)

        selected = router.select_gateway()
        routes_count[selected] += 1

        gw = gateways[selected]
        success, latency = await gw.execute_payment()
        router.feedback(selected, latency, success)

        if success:
            successes += 1

        if (i + 1) % 250 == 0:
            print(f"Txn {i+1}/{total_txns} | Distribution: {routes_count}")

    print("\n--- Simulation Complete ---")
    print(f"Overall Success Rate: {(successes / total_txns) * 100:.2f}%")
    print(f"Final Route Distribution: {routes_count}")
    print("\nFinal Telemetry State:")
    for gw, m in router.get_all_metrics().items():
        print(f"  {gw}: SR={m['success_rate']*100:.1f}%, P95={m['p95_ms']:.1f}ms, (a={m['alpha']}, b={m['beta']})")


if __name__ == "__main__":
    asyncio.run(run_benchmark())