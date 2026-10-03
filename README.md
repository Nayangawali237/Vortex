# Vortex
– Multi-Armed Bandit Smart Payment Router The One-Liner: "Payment gateways don't just crash—they bleed latency. VortexRoute dynamically routes millions of UPI transactions away from degrading banks in real time using a self-learning probabilistic algorithm."


📌 Executive SummaryIn high-throughput digital commerce (UPI, card acquiring, and instant transfers), payment gateways rarely crash with a clean HTTP $500$ error. Instead, downstream Core Banking Systems (CBS) bleed latency: queue depths saturate, response times climb from $110\text{ ms}$ to $1,800+\text{ ms}$, and transactions hang in non-deterministic pending states until customers abandon their carts.Traditional architectures rely on static priority waterfalls or naive threshold-based circuit breakers (e.g., "trip if 5 consecutive errors occur"). These mechanisms fail catastrophically during partial slowdowns because slow requests still return partial successes, starving the failover trigger while trapping thousands of customers on frozen loading screens.VortexRoute replaces brittle if/else logic with Discounted Multi-Objective Thompson Sampling (Multi-Armed Bandit). It:Continuously models each bank pipeline's completion probability as a dynamic $\text{Beta}(\alpha, \beta)$ distribution.Evacuates $90\%$ of traffic away from degrading banks within $3\text{ to }5\text{ seconds}$ using rolling P95 telemetry.Keeps a $5\%\text{ to }10\%$ autonomous micro-probe stream active on degraded pipes to detect system recovery without manual engineering intervention.Exploits MDR (Merchant Discount Rate) fee arbitrage, automatically selecting cheaper routes when reliability and latency across acquirers are equivalent.




                  ┌───────────────────────────────────────────────┐
                  │   Client Ingestion Layer (iOS / Android / Web)│
                  └───────────────────────┬───────────────────────┘
                                          │ POST /v1/pay
                                          ▼
               ┌────────────────────────────────────────────────────────────────────────────────────────┐
               │                                 VortexRoute Core Engine                                │
               │                                                                                        │
              c│   ┌──────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────┐   │
               │   │   Idempotency Registry   │───►│ Thompson Sampling Router│───►│ Multi-Objective │   │
               │   │ (Zero Double-Debit Guard)│    │ (Discounted Beta Priors)│    │ Utility Scorer  │   │
               │   └──────────────────────────┘    └─────────────────────────┘    └────────┬────────┘   │
               │                 ▲                                                         │            │
               │                 │ Updates State                                 Picks Best│            │
               │                 │                                                         ▼            │
               │   ┌─────────────┴────────────┐                           ┌─────────────────────────┐   │
               │   │ Sliding-Window Telemetry │◄──────────────────────────│  Acquiring Gateway Pool │   │
               │   │(Ring Buffer: P50/P95/P99)│   Feedback (lat, ok, fee) │ (HDFC, ICICI, Axis, RP) │   │
               │   └──────────────────────────┘                           └────────────┬────────────┘   │
               └───────────────────────────────────────────────────────────────────────┼────────────────┘
                                                                        │
                         ┌──────────────────────┬───────────────────────┴───────────────┐
                         ▼                      ▼                                       ▼
               ┌──────────────────┐   ┌──────────────────┐                    ┌──────────────────┐
               │   HDFC Direct    │   │   ICICI Stack    │                    │     Axis Neo     │
               │  (1.20% MDR Pipe)│   │  (1.10% MDR Pipe)│                    │  (0.90% MDR Pipe)│
               └─────────┬────────┘   └─────────┬────────┘                    └─────────┬────────┘
                         │                      │                                       │
                         └──────────────────────┴───────────────────┬───────────────────┘
                                                                    ▼
                                                     ┌─────────────────────────────┐
                                                     │  NPCI Central UPI Switch    │
                                                     └──────────────┬──────────────┘
                                                                    ▼
                                                     ┌─────────────────────────────┐
                                                     │ Issuer Bank (Customer Acct) │
                                                     └─────────────────────────────┘
