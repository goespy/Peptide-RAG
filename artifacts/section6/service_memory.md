# Service Memory Benchmark

- Measured: `2026-08-17T02:04:38.858784Z`
- Platform: `Windows-11-10.0.26200-SP0`
- Python: `3.12.13`
- Cache: `artifacts/section5/embeddings_256_64.npz`
- Documents: `2000`
- Startup: `3514.957 ms`
- RSS before load: `41,197,568 bytes`
- RSS after load: `217,751,552 bytes`
- RSS delta: `176,553,984 bytes`
- Peak process RSS: `278,065,152 bytes`
- Semantic retrieval available: `true`
- Grounded generation available: `false`
- Provider calls: `0`

This is an observed cold-start footprint on one development machine, not a
Railway service-level guarantee. Railway memory must still be checked after deployment.
