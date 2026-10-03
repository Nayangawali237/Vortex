import asyncio
import json
import random
import time
import uuid
from typing import Dict, List, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine.bandit import VortexRouter
from engine.state_machine import IdempotencyRegistry, PaymentState
from gateways.mock_gateways import MockBankGateway

app = FastAPI(
    title="VortexRoute Live Payment Switch",
    description="Multi-Armed Bandit Smart Payment Router with Live WebSocket Telemetry",
    version="1.0.0"
)

# Enable CORS for local browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    """Manages active browser WebSocket subscribers."""
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        dead_sockets = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                dead_sockets.append(connection)
        for dead in dead_sockets:
            self.active_connections.discard(dead)

manager = ConnectionManager()

router = VortexRouter(
    strategy="thompson_sampling",
    latency_budget_ms=1000.0,
    w_success=1.0,
    w_latency=0.35,
    w_cost=0.20
)
registry = IdempotencyRegistry()

# Configure bank gateways matching the Cirrus dashboard
gateways: Dict[str, MockBankGateway] = {
    "HDFC": MockBankGateway("HDFC", base_latency_ms=110.0, base_success_rate=0.995, mdr_rate=0.012),
    "ICICI": MockBankGateway("ICICI", base_latency_ms=130.0, base_success_rate=0.990, mdr_rate=0.011),
    "AXIS": MockBankGateway("AXIS", base_latency_ms=155.0, base_success_rate=0.982, mdr_rate=0.009),
    "RAZORPAY": MockBankGateway("RAZORPAY", base_latency_ms=165.0, base_success_rate=0.994, mdr_rate=0.018),
}

for name, gw in gateways.items():
    router.register_gateway(name, base_mdr=gw.mdr_rate)

class PaymentRequest(BaseModel):
    idempotency_key: str = Field(..., description="Unique idempotency identifier from client app")
    amount: float = Field(..., gt=0, description="Transaction ticket size in INR")
    remitter_vpa: str = Field(..., description="Virtual Payment Address of customer")

class FaultInjectionRequest(BaseModel):
    gateway_id: str
    is_degraded: bool
    latency_ms: float = 1350.0
    success_rate: float = 0.55

@app.post("/v1/pay")
async def execute_payment(req: PaymentRequest):
    # 1. Idempotency Check
    cached = registry.get(req.idempotency_key)
    if cached and cached.state in [PaymentState.SUCCESS, PaymentState.IN_FLIGHT]:
        return {
            "txn_id": cached.txn_id,
            "idempotency_key": cached.idempotency_key,
            "gateway": cached.gateway,
            "state": cached.state.value,
            "is_duplicate_replay": True,
            "latency_ms": cached.latency_ms,
        }

    # 2. Dynamic Routing Selection via Thompson Sampling
    chosen_gateway = router.select_gateway()
    txn_id = f"txn_{uuid.uuid4().hex[:10].upper()}"

    registry.get_or_create(req.idempotency_key, txn_id, req.amount, req.remitter_vpa, chosen_gateway)
    registry.transition(req.idempotency_key, PaymentState.IN_FLIGHT)

    # 3. Bank Execution via Adapter
    gw = gateways[chosen_gateway]
    status, is_success, latency_ms, fee = gw.execute_payment(req.amount)

    target_state = (
        PaymentState.SUCCESS if status == "SUCCESS"
        else (PaymentState.TIMEOUT_PENDING if status == "TIMEOUT_PENDING" else PaymentState.FAILED)
    )
    registry.transition(req.idempotency_key, target_state, latency_ms=latency_ms)

    # 4. Online Bayesian Feedback
    router.feedback(chosen_gateway, is_success, latency_ms, gw.mdr_rate, status)

    arm = router.arms[chosen_gateway]
    score = arm.sample_success_probability()

    # 5. Broadcast to Connected Cirrus Dashboards via WebSocket
    event_payload = {
        "txn_id": txn_id,
        "vpa": req.remitter_vpa,
        "amount_raw": req.amount,
        "gateway": chosen_gateway,
        "status": status,
        "latency_ms": latency_ms,
        "fee": fee,
        "score": score,
        "alpha": arm.alpha,
        "beta": arm.beta,
    }
    await manager.broadcast(event_payload)

    return {
        "txn_id": txn_id,
        "status": status,
        "gateway": chosen_gateway,
        "latency_ms": round(latency_ms, 2),
        "fee_charged": round(fee, 2),
    }

@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection open; receive heartbeats
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/v1/admin/fault-injection")
async def inject_fault(req: FaultInjectionRequest):
    if req.gateway_id not in gateways:
        raise HTTPException(status_code=404, detail="Gateway not found")
    gw = gateways[req.gateway_id]
    gw.set_degraded(req.is_degraded, latency=req.latency_ms, success_rate=req.success_rate)
    return {
        "gateway": req.gateway_id,
        "is_degraded": req.is_degraded,
        "current_latency_ms": gw.degraded_latency_ms if req.is_degraded else gw.base_latency_ms
    }

@app.get("/v1/telemetry")
def get_telemetry():
    report = {}
    for name, arm in router.arms.items():
        stats = arm.telemetry.compute_stats()
        report[name] = {
            "alpha": round(arm.alpha, 2),
            "beta": round(arm.beta, 2),
            "success_rate_pct": round(stats["success_rate"] * 100, 2),
            "p95_latency_ms": round(stats["p95_latency_ms"], 1),
            "routes_count": stats["count"]
        }
    return report

@app.get("/health")
def health():
    return {"status": "healthy", "service": "VortexRoute Switch"}