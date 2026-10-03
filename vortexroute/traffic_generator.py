import asyncio
import random
import time
import uuid
import httpx

API_URL = "http://localhost:8000/v1/pay"
FAULT_URL = "http://localhost:8000/v1/admin/fault-injection"

VPA_HANDLES = ["@okhdfcbank", "@okicici", "@okaxis", "@paytm", "@ibl", "@ybl"]
CUSTOMER_NAMES = ["arjun", "neha", "rohit", "priya", "vikram", "ananya", "siddharth", "pooja"]

async def dispatch_single_payment(client: httpx.AsyncClient, txn_idx: int):
    name = random.choice(CUSTOMER_NAMES)
    handle = random.choice(VPA_HANDLES)
    vpa = f"{name}{random.randint(10, 99)}{handle}"
    amount = round(random.uniform(150.0, 4800.0), 2)
    idempotency_key = f"order_{uuid.uuid4().hex[:12]}"

    payload = {
        "idempotency_key": idempotency_key,
        "amount": amount,
        "remitter_vpa": vpa
    }

    try:
        resp = await client.post(API_URL, json=payload, timeout=3.0)
        data = resp.json()
        gw = data.get("gateway")
        status = data.get("status")
        lat = data.get("latency_ms")
        fee = data.get("fee_charged")

        color_code = "\033[92m" if status == "SUCCESS" else "\033[91m"
        print(f"[{txn_idx:04d}] {color_code}{status:<15}\033[0m | Gateway: {gw:<8} | Latency: {lat:>6.1f}ms | Amount: ₹{amount:>7.2f} | Fee: ₹{fee:>5.2f}")
    except Exception as e:
        print(f"[{txn_idx:04d}] \033[91mDISPATCH_ERROR\033[0m: {e}")

async def run_traffic_stream(tps: int = 15, duration_seconds: int = 60):
    print("\n" + "=" * 80)
    print("  VortexRoute: Live High-Concurrency Traffic Stream")
    print(f"  Target: {API_URL}")
    print(f"  Rate: {tps} transactions/sec | Duration: {duration_seconds}s")
    print("=" * 80 + "\n")

    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    async with httpx.AsyncClient(limits=limits) as client:
        start_time = time.time()
        txn_counter = 0

        while (time.time() - start_time) < duration_seconds:
            elapsed = time.time() - start_time

            # Automatically inject CBS Brownout on HDFC between 15s and 35s
            if 15.0 <= elapsed <= 15.5:
                print("\n\033[93m>>> INJECTING BROWNOUT ON HDFC DIRECT (CBS latency -> 1350ms, SR -> 55%) <<<\033[0m\n")
                await client.post(FAULT_URL, json={"gateway_id": "HDFC", "is_degraded": True, "latency_ms": 1350.0, "success_rate": 0.55})

            # Recover HDFC after 35s
            if 35.0 <= elapsed <= 35.5:
                print("\n\033[92m>>> RECOVERING HDFC DIRECT (Restored to 110ms normal latency) <<<\033[0m\n")
                await client.post(FAULT_URL, json={"gateway_id": "HDFC", "is_degraded": False})

            batch = [dispatch_single_payment(client, txn_counter + i) for i in range(tps)]
            txn_counter += tps
            await asyncio.gather(*batch)
            await asyncio.sleep(1.0)

    print("\n" + "=" * 80)
    print("  Traffic Stream Complete!")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    asyncio.run(run_traffic_stream(tps=12, duration_seconds=50))