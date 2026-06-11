# HandMouse Telemetry

- All new telemetry events use `schema_version = 2`.
- `frame_sample` records image landmarks as `[x, y, z]` and world landmarks as `[x, y, z]`.
- `gesture_decision` is emitted for both committed and blocked candidates, with `blocked_by`, `quality_score`, and `quality_reasons`.
- `gesture_candidate` records detector-phase output before policy.
- `action_dispatch` records the final routed side effect after policy.
