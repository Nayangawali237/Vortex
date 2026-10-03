import enum
import time
from typing import Dict, Optional
from dataclasses import dataclass

class PaymentState(str, enum.Enum):
    INITIATED = "INITIATED"
    IN_FLIGHT = "IN_FLIGHT"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT_PENDING = "TIMEOUT_PENDING"

TransactionState = PaymentState

@dataclass
class TransactionRecord:
    txn_id: str
    idempotency_key: str
    amount: float
    remitter_vpa: str
    gateway: str
    state: PaymentState
    created_at: float
    updated_at: float
    latency_ms: float = 0.0

class IdempotencyRegistry:
    def __init__(self):
        self._records: Dict[str, TransactionRecord] = {}

    def get_or_create(self, idempotency_key: str, txn_id: str, amount: float, remitter_vpa: str, gateway: str) -> TransactionRecord:
        if idempotency_key in self._records:
            return self._records[idempotency_key]
        now = time.time()
        rec = TransactionRecord(
            txn_id=txn_id,
            idempotency_key=idempotency_key,
            amount=amount,
            remitter_vpa=remitter_vpa,
            gateway=gateway,
            state=PaymentState.INITIATED,
            created_at=now,
            updated_at=now
        )
        self._records[idempotency_key] = rec
        return rec

    def transition(self, idempotency_key: str, target_state: PaymentState, latency_ms: float = 0.0) -> TransactionRecord:
        rec = self._records[idempotency_key]
        rec.state = target_state
        rec.latency_ms = latency_ms
        rec.updated_at = time.time()
        return rec

    def get(self, idempotency_key: str) -> Optional[TransactionRecord]:
        return self._records.get(idempotency_key)

IdempotencyStore = IdempotencyRegistry
