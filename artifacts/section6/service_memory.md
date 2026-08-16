# Service Memory Benchmark

- Measured: `2026-08-16T20:21:23.883744Z`
- Platform: `Windows-11-10.0.26200-SP0`
- Python: `3.12.13`
- Cache: `artifacts/section5/embeddings_256_64.npz`
- Documents: `2000`
- Startup: `3519.262 ms`
- RSS before load: `41,312,256 bytes`
- RSS after load: `216,748,032 bytes`
- RSS delta: `175,435,776 bytes`
- Peak process RSS: `278,310,912 bytes`
- Semantic retrieval available: `true`
- Grounded generation available: `false`
- Provider calls: `0`

This is an observed cold-start footprint on one development machine, not a
Railway service-level guarantee. Railway memory must still be checked after deployment.
