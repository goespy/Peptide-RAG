# Service Memory Benchmark

- Measured: `2026-08-17T15:08:29.142089Z`
- Platform: `Windows-11-10.0.26200-SP0`
- Python: `3.12.13`
- Cache: `artifacts/section5/embeddings_256_64.npz`
- Documents: `2000`
- Startup: `3482.187 ms`
- RSS before load: `41,349,120 bytes`
- RSS after load: `218,300,416 bytes`
- RSS delta: `176,951,296 bytes`
- Peak process RSS: `278,355,968 bytes`
- Semantic retrieval available: `true`
- Grounded generation available: `false`
- Provider calls: `0`

This is an observed cold-start footprint on one development machine, not a
Railway service-level guarantee. Railway memory must still be checked after deployment.
