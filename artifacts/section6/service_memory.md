# Service Memory Benchmark

- Measured: `2026-08-17T22:51:52.798799Z`
- Platform: `Windows-11-10.0.26200-SP0`
- Python: `3.12.13`
- Cache: `artifacts/section5/embeddings_256_64.npz`
- Documents: `2000`
- Startup: `3582.723 ms`
- RSS before load: `41,209,856 bytes`
- RSS after load: `217,960,448 bytes`
- RSS delta: `176,750,592 bytes`
- Peak process RSS: `278,568,960 bytes`
- Semantic retrieval available: `true`
- Grounded generation available: `true`
- Provider calls: `0`

This is an observed cold-start footprint on one development machine, not a
Railway service-level guarantee. Compare it with the separate live Railway
snapshot; neither short measurement is a capacity test.
