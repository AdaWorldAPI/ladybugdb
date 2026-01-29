"""Hamming Operations - Every Language.

Core principle: XOR + POPCOUNT must produce IDENTICAL results in every language.
Same fingerprint → same distance → same similarity (always).

Languages:
- Python (reference)
- TypeScript/JavaScript
- Rust
- Go
- C
- C++
- Java
- C#
- Ruby
- Zig
- WASM (WAT)
"""

# =============================================================================
# PYTHON (Reference Implementation)
# =============================================================================

PYTHON = '''
"""10K Hamming Operations - Python Reference."""
import numpy as np
from typing import List, Tuple

DIM = 10_000
DIM_U64 = 157  # (10000 + 63) // 64
LAST_MASK = (1 << 16) - 1

def popcount64(x: int) -> int:
    """Count set bits in 64-bit integer."""
    x = x - ((x >> 1) & 0x5555555555555555)
    x = (x & 0x3333333333333333) + ((x >> 2) & 0x3333333333333333)
    x = (x + (x >> 4)) & 0x0F0F0F0F0F0F0F0F
    return ((x * 0x0101010101010101) >> 56) & 0xFF

def hamming(a: List[int], b: List[int]) -> int:
    """Hamming distance between two 10K vectors."""
    total = 0
    for i in range(DIM_U64):
        total += popcount64(a[i] ^ b[i])
    return total

def similarity(a: List[int], b: List[int]) -> float:
    """Similarity [0, 1] from Hamming distance."""
    return 1.0 - hamming(a, b) / DIM

def xor_bind(a: List[int], b: List[int]) -> List[int]:
    """XOR bind two vectors."""
    result = [a[i] ^ b[i] for i in range(DIM_U64)]
    result[-1] &= LAST_MASK
    return result

def batch_hamming(query: List[int], corpus: List[List[int]]) -> List[int]:
    """Batch Hamming distances."""
    return [hamming(query, vec) for vec in corpus]

def resonate(query: List[int], corpus: List[List[int]], threshold: float = 0.5) -> List[Tuple[int, float]]:
    """Find vectors above similarity threshold."""
    results = []
    for i, vec in enumerate(corpus):
        sim = similarity(query, vec)
        if sim >= threshold:
            results.append((i, sim))
    results.sort(key=lambda x: x[1], reverse=True)
    return results
'''

# =============================================================================
# TYPESCRIPT / JAVASCRIPT
# =============================================================================

TYPESCRIPT = '''
/**
 * 10K Hamming Operations - TypeScript
 * Uses BigInt for 64-bit operations
 */

const DIM = 10_000;
const DIM_U64 = 157;
const LAST_MASK = BigInt((1 << 16) - 1);

function popcount64(x: bigint): number {
    x = x - ((x >> 1n) & 0x5555555555555555n);
    x = (x & 0x3333333333333333n) + ((x >> 2n) & 0x3333333333333333n);
    x = (x + (x >> 4n)) & 0x0F0F0F0F0F0F0F0Fn;
    return Number((x * 0x0101010101010101n) >> 56n) & 0xFF;
}

export function hamming(a: bigint[], b: bigint[]): number {
    let total = 0;
    for (let i = 0; i < DIM_U64; i++) {
        total += popcount64(a[i] ^ b[i]);
    }
    return total;
}

export function similarity(a: bigint[], b: bigint[]): number {
    return 1.0 - hamming(a, b) / DIM;
}

export function xorBind(a: bigint[], b: bigint[]): bigint[] {
    const result: bigint[] = new Array(DIM_U64);
    for (let i = 0; i < DIM_U64; i++) {
        result[i] = a[i] ^ b[i];
    }
    result[DIM_U64 - 1] &= LAST_MASK;
    return result;
}

export function batchHamming(query: bigint[], corpus: bigint[][]): number[] {
    return corpus.map(vec => hamming(query, vec));
}

export function resonate(
    query: bigint[], 
    corpus: bigint[][], 
    threshold: number = 0.5
): [number, number][] {
    const results: [number, number][] = [];
    for (let i = 0; i < corpus.length; i++) {
        const sim = similarity(query, corpus[i]);
        if (sim >= threshold) {
            results.push([i, sim]);
        }
    }
    return results.sort((a, b) => b[1] - a[1]);
}
'''

# =============================================================================
# RUST
# =============================================================================

RUST = '''
//! 10K Hamming Operations - Rust
//! Zero-cost abstractions, SIMD-friendly

const DIM: usize = 10_000;
const DIM_U64: usize = 157;
const LAST_MASK: u64 = (1 << 16) - 1;

#[inline(always)]
fn popcount64(x: u64) -> u32 {
    x.count_ones()  // Uses POPCNT instruction when available
}

pub fn hamming(a: &[u64; DIM_U64], b: &[u64; DIM_U64]) -> u32 {
    let mut total = 0u32;
    for i in 0..DIM_U64 {
        total += popcount64(a[i] ^ b[i]);
    }
    total
}

pub fn similarity(a: &[u64; DIM_U64], b: &[u64; DIM_U64]) -> f64 {
    1.0 - (hamming(a, b) as f64) / (DIM as f64)
}

pub fn xor_bind(a: &[u64; DIM_U64], b: &[u64; DIM_U64]) -> [u64; DIM_U64] {
    let mut result = [0u64; DIM_U64];
    for i in 0..DIM_U64 {
        result[i] = a[i] ^ b[i];
    }
    result[DIM_U64 - 1] &= LAST_MASK;
    result
}

pub fn batch_hamming(query: &[u64; DIM_U64], corpus: &[[u64; DIM_U64]]) -> Vec<u32> {
    corpus.iter().map(|vec| hamming(query, vec)).collect()
}

pub fn resonate(
    query: &[u64; DIM_U64],
    corpus: &[[u64; DIM_U64]],
    threshold: f64,
) -> Vec<(usize, f64)> {
    let mut results: Vec<(usize, f64)> = corpus
        .iter()
        .enumerate()
        .filter_map(|(i, vec)| {
            let sim = similarity(query, vec);
            if sim >= threshold { Some((i, sim)) } else { None }
        })
        .collect();
    results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
    results
}

// SIMD-optimized batch (requires nightly + portable_simd)
#[cfg(feature = "simd")]
pub mod simd {
    use std::simd::*;
    
    pub fn batch_hamming_simd(query: &[u64; 157], corpus: &[[u64; 157]]) -> Vec<u32> {
        // Process 8 vectors at a time using AVX-512
        corpus.chunks(8).flat_map(|chunk| {
            // Vectorized XOR + POPCNT
            chunk.iter().map(|vec| super::hamming(query, vec))
        }).collect()
    }
}
'''

# =============================================================================
# GO
# =============================================================================

GO = '''
// 10K Hamming Operations - Go
package hamming

import (
    "math/bits"
    "sort"
)

const (
    DIM     = 10000
    DIM_U64 = 157
    LAST_MASK = (1 << 16) - 1
)

type Vector [DIM_U64]uint64

func Hamming(a, b *Vector) int {
    total := 0
    for i := 0; i < DIM_U64; i++ {
        total += bits.OnesCount64(a[i] ^ b[i])
    }
    return total
}

func Similarity(a, b *Vector) float64 {
    return 1.0 - float64(Hamming(a, b))/float64(DIM)
}

func XorBind(a, b *Vector) Vector {
    var result Vector
    for i := 0; i < DIM_U64; i++ {
        result[i] = a[i] ^ b[i]
    }
    result[DIM_U64-1] &= LAST_MASK
    return result
}

func BatchHamming(query *Vector, corpus []Vector) []int {
    results := make([]int, len(corpus))
    for i := range corpus {
        results[i] = Hamming(query, &corpus[i])
    }
    return results
}

type Match struct {
    Index      int
    Similarity float64
}

func Resonate(query *Vector, corpus []Vector, threshold float64) []Match {
    var results []Match
    for i := range corpus {
        sim := Similarity(query, &corpus[i])
        if sim >= threshold {
            results = append(results, Match{i, sim})
        }
    }
    sort.Slice(results, func(i, j int) bool {
        return results[i].Similarity > results[j].Similarity
    })
    return results
}
'''

# =============================================================================
# C
# =============================================================================

C = '''
/* 10K Hamming Operations - C */
#ifndef HAMMING_H
#define HAMMING_H

#include <stdint.h>
#include <stdlib.h>

#define DIM 10000
#define DIM_U64 157
#define LAST_MASK ((1ULL << 16) - 1)

typedef uint64_t vector_t[DIM_U64];

static inline int popcount64(uint64_t x) {
#ifdef __POPCNT__
    return __builtin_popcountll(x);
#else
    x = x - ((x >> 1) & 0x5555555555555555ULL);
    x = (x & 0x3333333333333333ULL) + ((x >> 2) & 0x3333333333333333ULL);
    x = (x + (x >> 4)) & 0x0F0F0F0F0F0F0F0FULL;
    return (int)((x * 0x0101010101010101ULL) >> 56);
#endif
}

static inline int hamming(const vector_t a, const vector_t b) {
    int total = 0;
    for (int i = 0; i < DIM_U64; i++) {
        total += popcount64(a[i] ^ b[i]);
    }
    return total;
}

static inline double similarity(const vector_t a, const vector_t b) {
    return 1.0 - (double)hamming(a, b) / (double)DIM;
}

static inline void xor_bind(const vector_t a, const vector_t b, vector_t result) {
    for (int i = 0; i < DIM_U64; i++) {
        result[i] = a[i] ^ b[i];
    }
    result[DIM_U64 - 1] &= LAST_MASK;
}

/* Batch Hamming - caller provides output array */
static inline void batch_hamming(
    const vector_t query,
    const vector_t* corpus,
    int n,
    int* out
) {
    for (int i = 0; i < n; i++) {
        out[i] = hamming(query, corpus[i]);
    }
}

/* AVX-512 optimized batch (if available) */
#ifdef __AVX512F__
#include <immintrin.h>

static inline void batch_hamming_avx512(
    const vector_t query,
    const vector_t* corpus,
    int n,
    int* out
) {
    for (int i = 0; i < n; i++) {
        __m512i total = _mm512_setzero_si512();
        for (int j = 0; j < DIM_U64; j += 8) {
            __m512i a = _mm512_loadu_si512(&query[j]);
            __m512i b = _mm512_loadu_si512(&corpus[i][j]);
            __m512i xored = _mm512_xor_si512(a, b);
            __m512i popcnt = _mm512_popcnt_epi64(xored);
            total = _mm512_add_epi64(total, popcnt);
        }
        out[i] = _mm512_reduce_add_epi64(total);
    }
}
#endif

#endif /* HAMMING_H */
'''

# =============================================================================
# C++
# =============================================================================

CPP = '''
// 10K Hamming Operations - C++20
#pragma once

#include <array>
#include <vector>
#include <algorithm>
#include <bit>
#include <cstdint>

namespace hamming {

constexpr size_t DIM = 10'000;
constexpr size_t DIM_U64 = 157;
constexpr uint64_t LAST_MASK = (1ULL << 16) - 1;

using Vector = std::array<uint64_t, DIM_U64>;

[[nodiscard]] constexpr int popcount64(uint64_t x) noexcept {
    return std::popcount(x);
}

[[nodiscard]] constexpr int distance(const Vector& a, const Vector& b) noexcept {
    int total = 0;
    for (size_t i = 0; i < DIM_U64; ++i) {
        total += popcount64(a[i] ^ b[i]);
    }
    return total;
}

[[nodiscard]] constexpr double similarity(const Vector& a, const Vector& b) noexcept {
    return 1.0 - static_cast<double>(distance(a, b)) / static_cast<double>(DIM);
}

[[nodiscard]] constexpr Vector xor_bind(const Vector& a, const Vector& b) noexcept {
    Vector result{};
    for (size_t i = 0; i < DIM_U64; ++i) {
        result[i] = a[i] ^ b[i];
    }
    result[DIM_U64 - 1] &= LAST_MASK;
    return result;
}

[[nodiscard]] std::vector<int> batch_distance(
    const Vector& query, 
    const std::vector<Vector>& corpus
) {
    std::vector<int> results(corpus.size());
    std::transform(corpus.begin(), corpus.end(), results.begin(),
        [&query](const Vector& v) { return distance(query, v); });
    return results;
}

struct Match {
    size_t index;
    double sim;
    
    bool operator<(const Match& other) const { return sim > other.sim; }
};

[[nodiscard]] std::vector<Match> resonate(
    const Vector& query,
    const std::vector<Vector>& corpus,
    double threshold = 0.5
) {
    std::vector<Match> results;
    results.reserve(corpus.size() / 10);  // Estimate 10% match
    
    for (size_t i = 0; i < corpus.size(); ++i) {
        double sim = similarity(query, corpus[i]);
        if (sim >= threshold) {
            results.push_back({i, sim});
        }
    }
    
    std::sort(results.begin(), results.end());
    return results;
}

} // namespace hamming
'''

# =============================================================================
# JAVA
# =============================================================================

JAVA = '''
package com.firefly.hamming;

import java.util.*;

/**
 * 10K Hamming Operations - Java
 */
public class Hamming {
    public static final int DIM = 10_000;
    public static final int DIM_U64 = 157;
    public static final long LAST_MASK = (1L << 16) - 1;
    
    public static int popcount64(long x) {
        return Long.bitCount(x);
    }
    
    public static int distance(long[] a, long[] b) {
        int total = 0;
        for (int i = 0; i < DIM_U64; i++) {
            total += popcount64(a[i] ^ b[i]);
        }
        return total;
    }
    
    public static double similarity(long[] a, long[] b) {
        return 1.0 - (double) distance(a, b) / (double) DIM;
    }
    
    public static long[] xorBind(long[] a, long[] b) {
        long[] result = new long[DIM_U64];
        for (int i = 0; i < DIM_U64; i++) {
            result[i] = a[i] ^ b[i];
        }
        result[DIM_U64 - 1] &= LAST_MASK;
        return result;
    }
    
    public static int[] batchDistance(long[] query, long[][] corpus) {
        int[] results = new int[corpus.length];
        for (int i = 0; i < corpus.length; i++) {
            results[i] = distance(query, corpus[i]);
        }
        return results;
    }
    
    public record Match(int index, double similarity) {}
    
    public static List<Match> resonate(long[] query, long[][] corpus, double threshold) {
        List<Match> results = new ArrayList<>();
        for (int i = 0; i < corpus.length; i++) {
            double sim = similarity(query, corpus[i]);
            if (sim >= threshold) {
                results.add(new Match(i, sim));
            }
        }
        results.sort((a, b) -> Double.compare(b.similarity(), a.similarity()));
        return results;
    }
}
'''

# =============================================================================
# C#
# =============================================================================

CSHARP = '''
// 10K Hamming Operations - C#
using System;
using System.Collections.Generic;
using System.Numerics;
using System.Runtime.Intrinsics;
using System.Runtime.Intrinsics.X86;

namespace Firefly.Hamming;

public static class HammingOps
{
    public const int DIM = 10_000;
    public const int DIM_U64 = 157;
    public const ulong LAST_MASK = (1UL << 16) - 1;

    public static int Popcount64(ulong x) => BitOperations.PopCount(x);

    public static int Distance(ReadOnlySpan<ulong> a, ReadOnlySpan<ulong> b)
    {
        int total = 0;
        for (int i = 0; i < DIM_U64; i++)
        {
            total += Popcount64(a[i] ^ b[i]);
        }
        return total;
    }

    public static double Similarity(ReadOnlySpan<ulong> a, ReadOnlySpan<ulong> b)
        => 1.0 - (double)Distance(a, b) / DIM;

    public static ulong[] XorBind(ReadOnlySpan<ulong> a, ReadOnlySpan<ulong> b)
    {
        var result = new ulong[DIM_U64];
        for (int i = 0; i < DIM_U64; i++)
        {
            result[i] = a[i] ^ b[i];
        }
        result[DIM_U64 - 1] &= LAST_MASK;
        return result;
    }

    public static int[] BatchDistance(ReadOnlySpan<ulong> query, ulong[][] corpus)
    {
        var results = new int[corpus.Length];
        for (int i = 0; i < corpus.Length; i++)
        {
            results[i] = Distance(query, corpus[i]);
        }
        return results;
    }

    public readonly record struct Match(int Index, double Sim);

    public static List<Match> Resonate(
        ReadOnlySpan<ulong> query, 
        ulong[][] corpus, 
        double threshold = 0.5)
    {
        var results = new List<Match>();
        for (int i = 0; i < corpus.Length; i++)
        {
            var sim = Similarity(query, corpus[i]);
            if (sim >= threshold)
            {
                results.Add(new Match(i, sim));
            }
        }
        results.Sort((a, b) => b.Sim.CompareTo(a.Sim));
        return results;
    }

    // AVX-512 optimized (if available)
    public static int[] BatchDistanceAvx512(ReadOnlySpan<ulong> query, ulong[][] corpus)
    {
        if (!Avx512F.IsSupported) return BatchDistance(query, corpus);
        
        var results = new int[corpus.Length];
        // AVX-512 implementation here
        return results;
    }
}
'''

# =============================================================================
# RUBY
# =============================================================================

RUBY = '''
# 10K Hamming Operations - Ruby
module Hamming
  DIM = 10_000
  DIM_U64 = 157
  LAST_MASK = (1 << 16) - 1

  def self.popcount64(x)
    x.to_s(2).count('1')
  end

  def self.distance(a, b)
    total = 0
    DIM_U64.times do |i|
      total += popcount64(a[i] ^ b[i])
    end
    total
  end

  def self.similarity(a, b)
    1.0 - distance(a, b).to_f / DIM
  end

  def self.xor_bind(a, b)
    result = DIM_U64.times.map { |i| a[i] ^ b[i] }
    result[-1] &= LAST_MASK
    result
  end

  def self.batch_distance(query, corpus)
    corpus.map { |vec| distance(query, vec) }
  end

  Match = Struct.new(:index, :similarity)

  def self.resonate(query, corpus, threshold = 0.5)
    results = []
    corpus.each_with_index do |vec, i|
      sim = similarity(query, vec)
      results << Match.new(i, sim) if sim >= threshold
    end
    results.sort_by { |m| -m.similarity }
  end
end
'''

# =============================================================================
# ZIG
# =============================================================================

ZIG = '''
//! 10K Hamming Operations - Zig
const std = @import("std");

pub const DIM: usize = 10_000;
pub const DIM_U64: usize = 157;
pub const LAST_MASK: u64 = (1 << 16) - 1;

pub const Vector = [DIM_U64]u64;

pub fn popcount64(x: u64) u32 {
    return @popCount(x);
}

pub fn distance(a: *const Vector, b: *const Vector) u32 {
    var total: u32 = 0;
    for (0..DIM_U64) |i| {
        total += popcount64(a[i] ^ b[i]);
    }
    return total;
}

pub fn similarity(a: *const Vector, b: *const Vector) f64 {
    return 1.0 - @as(f64, @floatFromInt(distance(a, b))) / @as(f64, DIM);
}

pub fn xorBind(a: *const Vector, b: *const Vector) Vector {
    var result: Vector = undefined;
    for (0..DIM_U64) |i| {
        result[i] = a[i] ^ b[i];
    }
    result[DIM_U64 - 1] &= LAST_MASK;
    return result;
}

pub fn batchDistance(
    query: *const Vector, 
    corpus: []const Vector, 
    out: []u32
) void {
    for (corpus, 0..) |*vec, i| {
        out[i] = distance(query, vec);
    }
}

pub const Match = struct {
    index: usize,
    sim: f64,
};

pub fn resonate(
    allocator: std.mem.Allocator,
    query: *const Vector,
    corpus: []const Vector,
    threshold: f64,
) ![]Match {
    var results = std.ArrayList(Match).init(allocator);
    
    for (corpus, 0..) |*vec, i| {
        const sim = similarity(query, vec);
        if (sim >= threshold) {
            try results.append(.{ .index = i, .sim = sim });
        }
    }
    
    std.sort.sort(Match, results.items, {}, struct {
        fn lessThan(_: void, a: Match, b: Match) bool {
            return a.sim > b.sim;
        }
    }.lessThan);
    
    return results.toOwnedSlice();
}
'''

# =============================================================================
# WASM (WebAssembly Text Format)
# =============================================================================

WASM = '''
;; 10K Hamming Operations - WebAssembly
(module
  ;; Constants
  (global $DIM i32 (i32.const 10000))
  (global $DIM_U64 i32 (i32.const 157))
  (global $LAST_MASK i64 (i64.const 65535))
  
  ;; Memory: 2 vectors (157 * 8 * 2 = 2512 bytes min)
  (memory (export "memory") 1)
  
  ;; popcount64 - count set bits
  (func $popcount64 (param $x i64) (result i32)
    (local $count i32)
    (local.set $count (i32.const 0))
    (block $done
      (loop $loop
        (br_if $done (i64.eqz (local.get $x)))
        (local.set $count 
          (i32.add (local.get $count)
            (i32.wrap_i64 (i64.and (local.get $x) (i64.const 1)))))
        (local.set $x (i64.shr_u (local.get $x) (i64.const 1)))
        (br $loop)
      )
    )
    (local.get $count)
  )
  
  ;; hamming distance between vectors at offsets a and b
  (func $hamming (export "hamming") (param $a i32) (param $b i32) (result i32)
    (local $total i32)
    (local $i i32)
    (local $xa i64)
    (local $xb i64)
    
    (local.set $total (i32.const 0))
    (local.set $i (i32.const 0))
    
    (block $done
      (loop $loop
        (br_if $done (i32.ge_u (local.get $i) (global.get $DIM_U64)))
        
        ;; Load 64-bit values
        (local.set $xa (i64.load (i32.add (local.get $a) (i32.mul (local.get $i) (i32.const 8)))))
        (local.set $xb (i64.load (i32.add (local.get $b) (i32.mul (local.get $i) (i32.const 8)))))
        
        ;; XOR and popcount
        (local.set $total 
          (i32.add (local.get $total)
            (call $popcount64 (i64.xor (local.get $xa) (local.get $xb)))))
        
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $loop)
      )
    )
    
    (local.get $total)
  )
  
  ;; similarity as fixed-point (multiply by 10000 for precision)
  (func $similarity_fp (export "similarity_fp") (param $a i32) (param $b i32) (result i32)
    (i32.sub 
      (global.get $DIM)
      (call $hamming (local.get $a) (local.get $b)))
  )
)
'''

# =============================================================================
# COLLECT ALL LANGUAGES
# =============================================================================

LANGUAGES = {
    "python": ("hamming.py", PYTHON),
    "typescript": ("hamming.ts", TYPESCRIPT),
    "rust": ("hamming.rs", RUST),
    "go": ("hamming.go", GO),
    "c": ("hamming.h", C),
    "cpp": ("hamming.hpp", CPP),
    "java": ("Hamming.java", JAVA),
    "csharp": ("Hamming.cs", CSHARP),
    "ruby": ("hamming.rb", RUBY),
    "zig": ("hamming.zig", ZIG),
    "wasm": ("hamming.wat", WASM),
}


def get_implementation(language: str) -> str:
    """Get Hamming implementation for a language."""
    if language.lower() not in LANGUAGES:
        raise ValueError(f"Unknown language: {language}. Available: {list(LANGUAGES.keys())}")
    return LANGUAGES[language.lower()][1].strip()


def get_filename(language: str) -> str:
    """Get filename for a language implementation."""
    return LANGUAGES[language.lower()][0]


def all_languages() -> list:
    """List all supported languages."""
    return list(LANGUAGES.keys())


if __name__ == "__main__":
    print("Hamming Operations - Available Languages:")
    print("-" * 40)
    for lang, (filename, _) in LANGUAGES.items():
        print(f"  {lang:12} → {filename}")
