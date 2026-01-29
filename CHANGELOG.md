# Changelog

All notable changes to LadybugDB will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Initial public release preparation
- Comprehensive documentation

---

## [0.1.0] - 2025-01-29

### Added

#### Core Engine
- **Unified Query Engine** - Single interface for SQL, Cypher, Vector, and Hamming queries
- **Cypher Transpiler** - Converts Cypher graph queries to SQL recursive CTEs
- **Variable-length path support** - `MATCH (a)-[:TYPE*1..5]->(b)` patterns
- **Butterfly detection** - Track causal amplification chains through graphs

#### Hamming SIMD Engine
- **AVX-512 acceleration** - 65M Hamming comparisons/sec
- **Zero-allocation search** - Pre-allocated BufferPool for hot path
- **Numba JIT compilation** - Native machine code via @njit decorators
- **10K-bit fingerprints** - 157 uint64 values per fingerprint

#### VSA Operations
- **BIND (XOR)** - Create compound representations
- **UNBIND** - Recover components from bound vectors
- **BUNDLE** - Majority vote for prototype creation
- **PERMUTE** - Encode sequence/position information
- **SEQUENCE** - Create ordered sequences of symbols

#### Compatibility Layer
- **Jina API** - `JinaClient`, `Document`, `DocumentArray`, `Flow`
- **Neo4j API** - `GraphDatabase`, `Session`, `Transaction`, `Result`
- **Pydantic-style DTOs** - `Node`, `Edge`, `Thought`, `Concept`, etc.
- **Agent coordination** - `Handover`, `Decision`, `Blocker` DTOs

#### Compression
- **Dictionary encoding** - For low-cardinality strings
- **Run-length encoding (RLE)** - For repeated values
- **Frame-of-reference (FOR)** - For small integers
- **Delta encoding** - For sequential/sorted data
- **Automatic selection** - Best encoding chosen per column
- **Chunk pruning** - Skip irrelevant chunks using statistics

#### Utilities
- **Content-based fingerprints** - SHA-256 + LFSR expansion
- **Semantic chunking** - Paragraph/sentence boundary detection
- **Fixed-size chunking** - With configurable overlap

### Documentation
- Quickstart guide
- Complete API reference
- Architecture deep dive
- Performance benchmarks
- Contributing guidelines

---

## [0.0.1] - 2025-01-28

### Added
- Initial prototype
- Basic Hamming distance implementation
- Simple SQL interface

---

## Roadmap

### [0.2.0] - Planned

- [ ] PostgreSQL wire protocol compatibility
- [ ] GPU acceleration (CUDA Hamming kernels)
- [ ] Distributed mode with Raft consensus
- [ ] Web UI for visualization
- [ ] More compression algorithms (Zstd, LZ4)

### [0.3.0] - Planned

- [ ] Kubernetes operator
- [ ] Prometheus metrics
- [ ] OpenTelemetry tracing
- [ ] Backup/restore tooling
- [ ] Schema migration system

### [1.0.0] - Planned

- [ ] Stable API guarantee
- [ ] Production hardening
- [ ] Enterprise features (RBAC, audit logs)
- [ ] Commercial support option

---

[Unreleased]: https://github.com/AdaWorldAPI/ladybugdb/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AdaWorldAPI/ladybugdb/releases/tag/v0.1.0
[0.0.1]: https://github.com/AdaWorldAPI/ladybugdb/releases/tag/v0.0.1
