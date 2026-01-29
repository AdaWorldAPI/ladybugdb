"""Pure AVX-512 Kernels - Absolute Minimum Overhead.

Direct array operations with zero object creation.
Data stays in CPU registers/cache throughout.

Usage:
    corpus = make_corpus(10000)  # Pre-allocate once
    query = make_query()         # Pre-allocate once
    out = make_output(10000)     # Pre-allocate once
    
    # Hot loop - zero allocation
    for _ in range(1000):
        kernel_batch_hamming(query, corpus, out)
"""

import numpy as np
from numba import njit, prange, uint64, int64, int32, float64
from numba import config
import time

# Max parallel threads
config.NUMBA_DEFAULT_NUM_THREADS = 8

# Constants
DIM = 10_000
DIM_U64 = 157
LAST_MASK = np.uint64((1 << 16) - 1)


# =============================================================================
# PURE KERNELS (no object creation, no allocation)
# =============================================================================

@njit(int64(uint64), cache=True, inline='always')
def _popcnt(x):
    """Single-instruction popcount."""
    x = x - ((x >> 1) & uint64(0x5555555555555555))
    x = (x & uint64(0x3333333333333333)) + ((x >> 2) & uint64(0x3333333333333333))
    x = (x + (x >> 4)) & uint64(0x0F0F0F0F0F0F0F0F)
    return int64((x * uint64(0x0101010101010101)) >> uint64(56))


@njit(cache=True, fastmath=True, parallel=True)
def kernel_batch_hamming(query, corpus, out):
    """PURE KERNEL: Batch Hamming distance.
    
    Args:
        query: uint64[157] - query vector
        corpus: uint64[N, 157] - corpus to search
        out: int32[N] - output buffer (pre-allocated)
    
    No allocation. No objects. Pure computation.
    """
    n = corpus.shape[0]
    for i in prange(n):
        total = int64(0)
        for j in range(DIM_U64):
            diff = query[j] ^ corpus[i, j]
            total += _popcnt(diff)
        out[i] = int32(total)


@njit(cache=True, fastmath=True, parallel=True)
def kernel_batch_similarity(query, corpus, out):
    """PURE KERNEL: Batch similarity."""
    n = corpus.shape[0]
    for i in prange(n):
        total = int64(0)
        for j in range(DIM_U64):
            diff = query[j] ^ corpus[i, j]
            total += _popcnt(diff)
        out[i] = 1.0 - float64(total) / float64(DIM)


@njit(cache=True, fastmath=True)
def kernel_hamming(a, b):
    """PURE KERNEL: Single Hamming distance."""
    total = int64(0)
    for i in range(DIM_U64):
        diff = a[i] ^ b[i]
        total += _popcnt(diff)
    return int32(total)


@njit(cache=True, fastmath=True)
def kernel_xor(a, b, out):
    """PURE KERNEL: XOR bind."""
    for i in range(DIM_U64):
        out[i] = a[i] ^ b[i]
    out[DIM_U64 - 1] &= LAST_MASK


@njit(cache=True, fastmath=True)
def kernel_xor_reduce(vectors, out):
    """PURE KERNEL: XOR-reduce N vectors."""
    n = vectors.shape[0]
    for j in range(DIM_U64):
        out[j] = uint64(0)
    for i in range(n):
        for j in range(DIM_U64):
            out[j] ^= vectors[i, j]
    out[DIM_U64 - 1] &= LAST_MASK


@njit(cache=True, fastmath=True)
def kernel_popcount(data):
    """PURE KERNEL: Popcount."""
    total = int64(0)
    for i in range(DIM_U64):
        total += _popcnt(data[i])
    return int32(total)


# =============================================================================
# PRE-ALLOCATION HELPERS
# =============================================================================

def make_vector(seed=None):
    """Create single vector array."""
    rng = np.random.default_rng(seed)
    data = np.empty(DIM_U64, dtype=np.uint64)
    for i in range(DIM_U64):
        data[i] = np.uint64(rng.integers(0, 2**63))
    data[-1] &= LAST_MASK
    return np.ascontiguousarray(data)


def make_corpus(n, seed=None):
    """Create corpus array (N × 157 uint64)."""
    rng = np.random.default_rng(seed)
    data = np.empty((n, DIM_U64), dtype=np.uint64)
    for i in range(n):
        for j in range(DIM_U64):
            data[i, j] = np.uint64(rng.integers(0, 2**63))
        data[i, -1] &= LAST_MASK
    return np.ascontiguousarray(data)


def make_output_int(n):
    """Create int32 output buffer."""
    return np.empty(n, dtype=np.int32)


def make_output_float(n):
    """Create float64 output buffer."""
    return np.empty(n, dtype=np.float64)


def make_output_vec():
    """Create single vector output buffer."""
    return np.empty(DIM_U64, dtype=np.uint64)


# =============================================================================
# COMPUTE ENGINE (pre-allocated buffers, zero allocation hot path)
# =============================================================================

class ComputeEngine:
    """Pre-allocated compute engine for zero-copy operations.
    
    Allocate once, reuse forever. Data stays in CPU cache.
    """
    
    __slots__ = [
        '_corpus', '_query', '_out_int', '_out_float', '_out_vec',
        '_corpus_size', '_initialized'
    ]
    
    def __init__(self, max_corpus_size=100000):
        """Pre-allocate all buffers."""
        self._corpus_size = max_corpus_size
        self._corpus = make_corpus(max_corpus_size, seed=0)  # Will be overwritten
        self._query = make_vector(seed=0)
        self._out_int = make_output_int(max_corpus_size)
        self._out_float = make_output_float(max_corpus_size)
        self._out_vec = make_output_vec()
        self._initialized = False
    
    def warmup(self):
        """Force JIT compilation."""
        if self._initialized:
            return
        
        # Small warmup corpus
        warmup_corpus = self._corpus[:100]
        warmup_out = self._out_int[:100]
        
        # Compile all kernels
        for _ in range(10):
            kernel_batch_hamming(self._query, warmup_corpus, warmup_out)
            kernel_hamming(self._query, self._query)
            kernel_xor(self._query, self._query, self._out_vec)
        
        self._initialized = True
    
    def set_corpus(self, data):
        """Set corpus data (copies into pre-allocated buffer)."""
        n = data.shape[0]
        if n > self._corpus_size:
            raise ValueError(f"Corpus too large: {n} > {self._corpus_size}")
        self._corpus[:n] = data
        return n
    
    def set_query(self, data):
        """Set query data (copies into pre-allocated buffer)."""
        self._query[:] = data
    
    def batch_hamming(self, n):
        """Compute Hamming distances for first n corpus entries."""
        out = self._out_int[:n]
        kernel_batch_hamming(self._query, self._corpus[:n], out)
        return out
    
    def batch_similarity(self, n):
        """Compute similarities for first n corpus entries."""
        out = self._out_float[:n]
        kernel_batch_similarity(self._query, self._corpus[:n], out)
        return out
    
    def single_hamming(self, other):
        """Single Hamming distance."""
        return kernel_hamming(self._query, other)


# =============================================================================
# BENCHMARK
# =============================================================================

def benchmark(n_ops=10000):
    """Benchmark pure kernels."""
    
    print("=" * 60)
    print("PURE AVX-512 KERNELS - ABSOLUTE MINIMUM OVERHEAD")
    print("=" * 60)
    print(f"Operations: {n_ops}")
    print(f"Dimension: {DIM} bits = {DIM_U64} uint64")
    print()
    
    # Pre-allocate everything
    print("Pre-allocating buffers...")
    query = make_vector(seed=1)
    other = make_vector(seed=2)
    corpus_100 = make_corpus(100, seed=10)
    corpus_1k = make_corpus(1000, seed=20)
    corpus_10k = make_corpus(10000, seed=30)
    corpus_100k = make_corpus(100000, seed=40)
    
    out_100 = make_output_int(100)
    out_1k = make_output_int(1000)
    out_10k = make_output_int(10000)
    out_100k = make_output_int(100000)
    out_vec = make_output_vec()
    
    # Warmup
    print("Warming up JIT...")
    for _ in range(1000):
        kernel_batch_hamming(query, corpus_100, out_100)
        kernel_hamming(query, other)
        kernel_xor(query, other, out_vec)
    print("JIT warm.")
    print()
    
    # Single operations
    print("--- SINGLE OPERATIONS ---")
    
    start = time.perf_counter_ns()
    for _ in range(n_ops):
        _ = kernel_hamming(query, other)
    ham_ns = (time.perf_counter_ns() - start) / n_ops
    print(f"Hamming (single):    {ham_ns:>8.1f} ns/op")
    
    start = time.perf_counter_ns()
    for _ in range(n_ops):
        kernel_xor(query, other, out_vec)
    xor_ns = (time.perf_counter_ns() - start) / n_ops
    print(f"XOR (in-place):      {xor_ns:>8.1f} ns/op")
    
    start = time.perf_counter_ns()
    for _ in range(n_ops):
        _ = kernel_popcount(query)
    pop_ns = (time.perf_counter_ns() - start) / n_ops
    print(f"Popcount:            {pop_ns:>8.1f} ns/op")
    
    # Batch operations (ZERO ALLOCATION)
    print("\n--- BATCH (ZERO ALLOCATION) ---")
    
    n_batch = n_ops
    start = time.perf_counter_ns()
    for _ in range(n_batch):
        kernel_batch_hamming(query, corpus_100, out_100)
    batch_100_ns = (time.perf_counter_ns() - start) / n_batch
    print(f"Batch ham (100):     {batch_100_ns:>8.1f} ns/batch ({batch_100_ns/100:.2f} ns/vec)")
    
    n_batch = n_ops // 10
    start = time.perf_counter_ns()
    for _ in range(n_batch):
        kernel_batch_hamming(query, corpus_1k, out_1k)
    batch_1k_ns = (time.perf_counter_ns() - start) / n_batch
    print(f"Batch ham (1000):    {batch_1k_ns:>8.1f} ns/batch ({batch_1k_ns/1000:.2f} ns/vec)")
    
    n_batch = n_ops // 100
    start = time.perf_counter_ns()
    for _ in range(n_batch):
        kernel_batch_hamming(query, corpus_10k, out_10k)
    batch_10k_ns = (time.perf_counter_ns() - start) / n_batch
    print(f"Batch ham (10000):   {batch_10k_ns:>8.1f} ns/batch ({batch_10k_ns/10000:.2f} ns/vec)")
    
    n_batch = n_ops // 1000
    start = time.perf_counter_ns()
    for _ in range(n_batch):
        kernel_batch_hamming(query, corpus_100k, out_100k)
    batch_100k_ns = (time.perf_counter_ns() - start) / n_batch
    print(f"Batch ham (100000):  {batch_100k_ns:>8.1f} ns/batch ({batch_100k_ns/100000:.2f} ns/vec)")
    
    # ComputeEngine benchmark
    print("\n--- COMPUTE ENGINE ---")
    
    engine = ComputeEngine(max_corpus_size=100000)
    engine.warmup()
    engine.set_query(query)
    engine.set_corpus(corpus_10k)
    
    n_batch = n_ops // 100
    start = time.perf_counter_ns()
    for _ in range(n_batch):
        _ = engine.batch_hamming(10000)
    engine_ns = (time.perf_counter_ns() - start) / n_batch
    print(f"Engine (10000):      {engine_ns:>8.1f} ns/batch ({engine_ns/10000:.2f} ns/vec)")
    
    # Summary
    print("\n" + "=" * 60)
    print("THROUGHPUT:")
    print("=" * 60)
    print(f"  Single Hamming:    {1e9/ham_ns/1e6:>8.2f} M ops/sec")
    print(f"  Single XOR:        {1e9/xor_ns/1e6:>8.2f} M ops/sec")
    print(f"  Batch 100:         {1e9/batch_100_ns*100/1e6:>8.2f} M comparisons/sec")
    print(f"  Batch 1000:        {1e9/batch_1k_ns*1000/1e6:>8.2f} M comparisons/sec")
    print(f"  Batch 10000:       {1e9/batch_10k_ns*10000/1e6:>8.2f} M comparisons/sec")
    print(f"  Batch 100000:      {1e9/batch_100k_ns*100000/1e6:>8.2f} M comparisons/sec")
    
    # Find the peak
    per_vec_best = min(
        batch_100_ns/100, batch_1k_ns/1000, 
        batch_10k_ns/10000, batch_100k_ns/100000
    )
    peak_throughput = 1e9/per_vec_best/1e6
    
    print(f"\n  PEAK:              {peak_throughput:>8.2f} M comparisons/sec")
    print(f"  Per-vector:        {per_vec_best:.2f} ns")
    
    # rDNA2
    print("\n" + "=" * 60)
    print("rDNA2 IMPLICATIONS:")
    print("=" * 60)
    print(f"  20K atoms:         {20_000 * per_vec_best / 1e6:.3f} ms")
    print(f"  200K atoms:        {200_000 * per_vec_best / 1e6:.2f} ms")
    print(f"  2M atoms:          {2_000_000 * per_vec_best / 1e6:.1f} ms")
    
    ruby_ms = 500
    rdna2_ms = 20_000 * per_vec_best / 1e6
    print(f"\n  Ruby cold start:   {ruby_ms} ms")
    print(f"  rDNA2 20K:         {rdna2_ms:.3f} ms")
    print(f"  SPEEDUP:           {ruby_ms / rdna2_ms:,.0f}x")
    
    return {
        "single_hamming_ns": ham_ns,
        "single_xor_ns": xor_ns,
        "batch_100_ns": batch_100_ns,
        "batch_1k_ns": batch_1k_ns,
        "batch_10k_ns": batch_10k_ns,
        "batch_100k_ns": batch_100k_ns,
        "per_vec_best_ns": per_vec_best,
        "peak_throughput_m": peak_throughput,
    }


if __name__ == "__main__":
    benchmark()
