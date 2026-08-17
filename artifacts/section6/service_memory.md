# Service Memory Benchmark

- Measured: `2026-08-17T21:32:08.270310Z`
- Platform: `Windows-11-10.0.26200-SP0`
- Python: `3.12.13`
- Cache: `artifacts/section5/embeddings_256_64.npz`
- Documents: `2000`
- Startup: `3616.166 ms`
- RSS before load: `41,222,144 bytes`
- RSS after load: `217,669,632 bytes`
- RSS delta: `176,447,488 bytes`
- Peak process RSS: `278,188,032 bytes`
- Semantic retrieval available: `true`
- Grounded generation available: `true`
- Provider calls: `0`

This is an observed cold-start footprint on one development machine, not a
Railway service-level guarantee. Railway memory must still be checked after deployment.
