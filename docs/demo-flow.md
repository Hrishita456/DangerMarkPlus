# Three-minute DANGER MARK+ demo

Open https://dq0ijb66nf6yb.cloudfront.net. Before presenting, open https://4pc12p8rt1.execute-api.ap-southeast-2.amazonaws.com/api/v1/health and wait for `status: ok`; the initial cold start can exceed the gateway timeout, so retry health after startup completes. The deployed browser journey was validated on 11 October 2026.

- **0:00–0:20 — Problem:** Flood signals alone do not tell authorities who loses access, where people could go or which route remains available. Open DANGER MARK+ and select the analysis run.
- **0:20–0:45 — Consequences:** Show the approximately 72,900-person exposure estimate. Explain that this is an illustrative 205 m terrain scenario using Delhi/Yamuna datasets, not a validated July 2023 reconstruction. Population information is approximately 1 km resolution.
- **0:45–1:25 — Action:** Select Janta Garden, open its plan and show the candidate school destination. Inspect the primary route, then switch to the independent backup; both come from the backend road graph analysis.
- **1:25–1:50 — Honest uncertainty:** Select Tibetan Colony to show no independent backup. Capacity and departure deadline remain unknown because verified capacity and closure schedules are absent. Travel time is not total evacuation duration.
- **1:50–2:15 — Evidence:** Open Flood Intelligence and show flood/road/locality overlays. Open Safe Sites: these are candidate public facilities, not verified official shelters.
- **2:15–2:35 — Workflow:** Preview an advisory. Names, route availability and uncertainty follow the selected plan. Issuance is simulated; nothing is sent.
- **2:35–3:00 — AWS:** Show CloudFront + private S3 frontend, API Gateway HTTP API + Lambda backend and ECR image with the compact data snapshot. Close with: flood signal → consequence → actionable evacuation intelligence, with uncertainty visible.

Do not present the system as production-certified disaster infrastructure, real-time evacuation authority guidance, a calibrated forecast, or verified shelter availability.
