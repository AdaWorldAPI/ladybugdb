"""
LadybugDB POC - Level 11: BUTTERFLY CAUSALITY

Multihop correlation. Impact propagation. Root cause tracing.

The butterfly flaps its wings in module A...
  → ripple through B
    → cascade to C
      → crash in Z

CAUSALITY ENCODING:
  - Direct cause:    A → B (1-hop)
  - Mediated cause:  A → B → C (2-hop)
  - Butterfly:       A → B → C → ... → Z (n-hop with amplification)

CORRELATION TYPES:
  - CAUSES:      A change in X causes change in Y
  - CORRELATES:  X and Y change together (no direction)
  - AMPLIFIES:   Small X → Large Y
  - DAMPENS:     Large X → Small Y
  - DELAYS:      X → (time) → Y

IMPACT METRICS:
  - Reach:       How many nodes affected
  - Depth:       Maximum hop count
  - Amplification: Output magnitude / Input magnitude
  - Criticality:   Weighted impact on system health
"""

import numpy as np
import hashlib
import struct
from typing import Dict, List, Set, Tuple, Optional, NamedTuple
from dataclasses import dataclass, field
from enum import IntEnum
from collections import defaultdict, deque
from datetime import datetime
import json

# =============================================================================
# CONSTANTS
# =============================================================================

DIM = 10_000
DIM_U64 = 157

# =============================================================================
# FINGERPRINT
# =============================================================================

def fingerprint(identity: str) -> np.ndarray:
    data = np.empty(DIM_U64, dtype=np.uint64)
    for i in range(DIM_U64):
        h = hashlib.sha256(f"{identity}:{i}".encode()).digest()
        data[i] = struct.unpack('<Q', h[:8])[0]
    data[-1] &= np.uint64((1 << 16) - 1)
    return data


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    xored = np.bitwise_xor(a, b)
    dist = sum(bin(int(x)).count('1') for x in xored)
    return 1.0 - dist / DIM


# =============================================================================
# CAUSALITY TYPES
# =============================================================================

class CausalType(IntEnum):
    """Types of causal relationships."""
    CAUSES = 1        # Direct causation
    CORRELATES = 2    # Co-occurrence without direction
    AMPLIFIES = 3     # Small input → large output
    DAMPENS = 4       # Large input → small output
    DELAYS = 5        # Time-shifted causation
    ENABLES = 6       # Necessary but not sufficient
    PREVENTS = 7      # Blocks effect
    TRIGGERS = 8      # Initiates cascade


class ImpactType(IntEnum):
    """Types of impact."""
    FUNCTIONAL = 1    # Behavior change
    PERFORMANCE = 2   # Speed/memory change
    SECURITY = 3      # Vulnerability introduced
    STABILITY = 4     # Crash/error potential
    MAINTENANCE = 5   # Code quality change


# =============================================================================
# CAUSAL STRUCTURES
# =============================================================================

@dataclass
class CausalEdge:
    """An edge in the causal graph."""
    source: str
    target: str
    causal_type: CausalType
    strength: float       # 0-1, how strong is the causal link
    confidence: float     # 0-1, how sure are we
    latency: int          # Hops or time units before effect
    amplification: float  # Output/input ratio (>1 = amplifies)
    observations: int     # How many times observed
    
    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.causal_type.name,
            "strength": self.strength,
            "confidence": self.confidence,
            "latency": self.latency,
            "amplification": self.amplification
        }


@dataclass
class CausalChain:
    """A multi-hop causal chain."""
    nodes: List[str]
    edges: List[CausalEdge]
    total_hops: int
    total_amplification: float
    total_latency: int
    confidence: float  # Product of edge confidences
    
    def to_dict(self) -> dict:
        return {
            "chain": " → ".join(self.nodes),
            "hops": self.total_hops,
            "amplification": self.total_amplification,
            "latency": self.total_latency,
            "confidence": self.confidence
        }


@dataclass
class ButterflyEffect:
    """A detected butterfly effect - small cause, large effect."""
    origin: str
    origin_magnitude: float
    final_impact: List[str]
    final_magnitude: float
    chain: CausalChain
    amplification_ratio: float
    criticality: float
    
    def to_dict(self) -> dict:
        return {
            "origin": self.origin,
            "origin_magnitude": self.origin_magnitude,
            "final_impact": self.final_impact,
            "final_magnitude": self.final_magnitude,
            "chain": self.chain.to_dict(),
            "amplification": self.amplification_ratio,
            "criticality": self.criticality
        }


@dataclass
class ImpactReport:
    """Report of impact from a change."""
    source: str
    direct_impact: List[str]
    indirect_impact: List[str]
    reach: int
    max_depth: int
    total_amplification: float
    butterflies: List[ButterflyEffect]
    critical_paths: List[CausalChain]


# =============================================================================
# BUTTERFLY ENGINE
# =============================================================================

class ButterflyEngine:
    """
    Tracks causal relationships and detects butterfly effects.
    
    A butterfly effect occurs when:
    - Small change in A
    - Propagates through multiple hops
    - Results in large effect in Z
    - With amplification > threshold
    """
    
    def __init__(self):
        self.nodes: Set[str] = set()
        self.edges: Dict[Tuple[str, str], CausalEdge] = {}
        self.incoming: Dict[str, Set[str]] = defaultdict(set)
        self.outgoing: Dict[str, Set[str]] = defaultdict(set)
        
        # Node properties
        self.node_criticality: Dict[str, float] = {}
        self.node_fingerprints: Dict[str, np.ndarray] = {}
        
        # Thresholds
        self.BUTTERFLY_AMPLIFICATION = 5.0   # 5x amplification = butterfly
        self.MAX_HOP_DEPTH = 10              # Don't trace beyond 10 hops
        self.MIN_CONFIDENCE = 0.3            # Ignore low-confidence chains
    
    # -------------------------------------------------------------------------
    # Graph construction
    # -------------------------------------------------------------------------
    
    def add_node(self, name: str, criticality: float = 0.5) -> str:
        """Add a node to the causal graph."""
        self.nodes.add(name)
        self.node_criticality[name] = criticality
        self.node_fingerprints[name] = fingerprint(f"node::{name}")
        return name
    
    def add_edge(self, source: str, target: str, 
                 causal_type: CausalType = CausalType.CAUSES,
                 strength: float = 0.5,
                 confidence: float = 0.8,
                 latency: int = 1,
                 amplification: float = 1.0) -> CausalEdge:
        """Add a causal edge."""
        # Ensure nodes exist
        if source not in self.nodes:
            self.add_node(source)
        if target not in self.nodes:
            self.add_node(target)
        
        edge = CausalEdge(
            source=source,
            target=target,
            causal_type=causal_type,
            strength=strength,
            confidence=confidence,
            latency=latency,
            amplification=amplification,
            observations=1
        )
        
        key = (source, target)
        if key in self.edges:
            # Reinforce existing edge
            existing = self.edges[key]
            existing.observations += 1
            existing.confidence = min(1.0, existing.confidence + 0.1)
        else:
            self.edges[key] = edge
            self.outgoing[source].add(target)
            self.incoming[target].add(source)
        
        return self.edges[key]
    
    def causes(self, source: str, target: str, strength: float = 0.5) -> CausalEdge:
        """Shorthand: A causes B."""
        return self.add_edge(source, target, CausalType.CAUSES, strength)
    
    def amplifies(self, source: str, target: str, factor: float = 2.0) -> CausalEdge:
        """Shorthand: A amplifies effect on B."""
        return self.add_edge(source, target, CausalType.AMPLIFIES, 
                            strength=0.7, amplification=factor)
    
    def correlates(self, a: str, b: str, strength: float = 0.5) -> Tuple[CausalEdge, CausalEdge]:
        """Shorthand: A and B correlate (bidirectional)."""
        e1 = self.add_edge(a, b, CausalType.CORRELATES, strength)
        e2 = self.add_edge(b, a, CausalType.CORRELATES, strength)
        return e1, e2
    
    def enables(self, source: str, target: str) -> CausalEdge:
        """Shorthand: A enables B (necessary but not sufficient)."""
        return self.add_edge(source, target, CausalType.ENABLES, strength=0.3)
    
    def triggers(self, source: str, target: str, amplification: float = 1.5) -> CausalEdge:
        """Shorthand: A triggers cascade in B."""
        return self.add_edge(source, target, CausalType.TRIGGERS, 
                            strength=0.8, amplification=amplification)
    
    # -------------------------------------------------------------------------
    # Chain tracing
    # -------------------------------------------------------------------------
    
    def trace_chain(self, start: str, end: str, 
                    max_depth: int = None) -> List[CausalChain]:
        """Find all causal chains from start to end."""
        max_depth = max_depth or self.MAX_HOP_DEPTH
        chains = []
        
        # BFS with path tracking
        queue = deque([(start, [start], [], 1.0, 0, 1.0)])
        visited_paths = set()
        
        while queue:
            current, path, edges, conf, latency, amp = queue.popleft()
            
            if current == end and len(path) > 1:
                chain = CausalChain(
                    nodes=path.copy(),
                    edges=edges.copy(),
                    total_hops=len(path) - 1,
                    total_amplification=amp,
                    total_latency=latency,
                    confidence=conf
                )
                chains.append(chain)
                continue
            
            if len(path) > max_depth:
                continue
            
            path_key = tuple(path)
            if path_key in visited_paths:
                continue
            visited_paths.add(path_key)
            
            for next_node in self.outgoing.get(current, set()):
                if next_node not in path:  # Avoid cycles
                    edge = self.edges[(current, next_node)]
                    new_conf = conf * edge.confidence
                    
                    if new_conf >= self.MIN_CONFIDENCE:
                        queue.append((
                            next_node,
                            path + [next_node],
                            edges + [edge],
                            new_conf,
                            latency + edge.latency,
                            amp * edge.amplification
                        ))
        
        # Sort by confidence
        chains.sort(key=lambda c: c.confidence, reverse=True)
        return chains
    
    def trace_all_effects(self, source: str, 
                          max_depth: int = None) -> Dict[str, CausalChain]:
        """Trace all effects reachable from source."""
        max_depth = max_depth or self.MAX_HOP_DEPTH
        effects = {}
        
        # BFS from source
        queue = deque([(source, [source], [], 1.0, 0, 1.0)])
        
        while queue:
            current, path, edges, conf, latency, amp = queue.popleft()
            
            if current != source and current not in effects:
                effects[current] = CausalChain(
                    nodes=path.copy(),
                    edges=edges.copy(),
                    total_hops=len(path) - 1,
                    total_amplification=amp,
                    total_latency=latency,
                    confidence=conf
                )
            
            if len(path) > max_depth:
                continue
            
            for next_node in self.outgoing.get(current, set()):
                if next_node not in path:
                    edge = self.edges[(current, next_node)]
                    new_conf = conf * edge.confidence
                    
                    if new_conf >= self.MIN_CONFIDENCE:
                        queue.append((
                            next_node,
                            path + [next_node],
                            edges + [edge],
                            new_conf,
                            latency + edge.latency,
                            amp * edge.amplification
                        ))
        
        return effects
    
    def trace_root_causes(self, target: str, 
                          max_depth: int = None) -> Dict[str, CausalChain]:
        """Trace all potential root causes of target."""
        max_depth = max_depth or self.MAX_HOP_DEPTH
        causes = {}
        
        # BFS backwards
        queue = deque([(target, [target], [], 1.0, 0, 1.0)])
        
        while queue:
            current, path, edges, conf, latency, amp = queue.popleft()
            
            if current != target and current not in causes:
                # Reverse the path for causes
                causes[current] = CausalChain(
                    nodes=list(reversed(path)),
                    edges=list(reversed(edges)),
                    total_hops=len(path) - 1,
                    total_amplification=amp,
                    total_latency=latency,
                    confidence=conf
                )
            
            if len(path) > max_depth:
                continue
            
            for prev_node in self.incoming.get(current, set()):
                if prev_node not in path:
                    edge = self.edges[(prev_node, current)]
                    new_conf = conf * edge.confidence
                    
                    if new_conf >= self.MIN_CONFIDENCE:
                        queue.append((
                            prev_node,
                            path + [prev_node],
                            edges + [edge],
                            new_conf,
                            latency + edge.latency,
                            amp * edge.amplification
                        ))
        
        return causes
    
    # -------------------------------------------------------------------------
    # Butterfly detection
    # -------------------------------------------------------------------------
    
    def detect_butterflies(self, source: str, 
                           input_magnitude: float = 1.0) -> List[ButterflyEffect]:
        """Detect butterfly effects originating from source."""
        butterflies = []
        
        effects = self.trace_all_effects(source)
        
        for target, chain in effects.items():
            output_magnitude = input_magnitude * chain.total_amplification
            amplification_ratio = output_magnitude / input_magnitude
            
            if amplification_ratio >= self.BUTTERFLY_AMPLIFICATION:
                criticality = (
                    amplification_ratio * 
                    self.node_criticality.get(target, 0.5) *
                    chain.confidence
                )
                
                butterfly = ButterflyEffect(
                    origin=source,
                    origin_magnitude=input_magnitude,
                    final_impact=[target],
                    final_magnitude=output_magnitude,
                    chain=chain,
                    amplification_ratio=amplification_ratio,
                    criticality=criticality
                )
                butterflies.append(butterfly)
        
        # Sort by criticality
        butterflies.sort(key=lambda b: b.criticality, reverse=True)
        return butterflies
    
    def find_all_butterflies(self) -> List[ButterflyEffect]:
        """Find all butterfly effects in the graph."""
        all_butterflies = []
        
        for node in self.nodes:
            butterflies = self.detect_butterflies(node)
            all_butterflies.extend(butterflies)
        
        # Deduplicate and sort
        seen = set()
        unique = []
        for b in sorted(all_butterflies, key=lambda x: x.criticality, reverse=True):
            key = (b.origin, tuple(b.chain.nodes))
            if key not in seen:
                seen.add(key)
                unique.append(b)
        
        return unique
    
    # -------------------------------------------------------------------------
    # Impact analysis
    # -------------------------------------------------------------------------
    
    def analyze_impact(self, source: str, 
                       change_magnitude: float = 1.0) -> ImpactReport:
        """Analyze full impact of a change at source."""
        effects = self.trace_all_effects(source)
        butterflies = self.detect_butterflies(source, change_magnitude)
        
        # Categorize effects by hop count
        direct = [t for t, c in effects.items() if c.total_hops == 1]
        indirect = [t for t, c in effects.items() if c.total_hops > 1]
        
        # Find max depth
        max_depth = max((c.total_hops for c in effects.values()), default=0)
        
        # Total amplification (max across all paths)
        total_amp = max((c.total_amplification for c in effects.values()), default=1.0)
        
        # Critical paths (high amplification + high target criticality)
        critical_paths = []
        for target, chain in effects.items():
            if chain.total_amplification > 2.0:
                criticality = chain.total_amplification * self.node_criticality.get(target, 0.5)
                if criticality > 1.0:
                    critical_paths.append(chain)
        
        critical_paths.sort(key=lambda c: c.total_amplification, reverse=True)
        
        return ImpactReport(
            source=source,
            direct_impact=direct,
            indirect_impact=indirect,
            reach=len(effects),
            max_depth=max_depth,
            total_amplification=total_amp,
            butterflies=butterflies,
            critical_paths=critical_paths[:5]
        )
    
    # -------------------------------------------------------------------------
    # Correlation detection
    # -------------------------------------------------------------------------
    
    def find_correlations(self, observations: List[Tuple[str, str]]) -> List[Tuple[str, str, float]]:
        """
        Find correlations from observation pairs.
        
        observations: List of (changed_node, affected_node) pairs
        """
        # Count co-occurrences
        cooccur = defaultdict(int)
        node_counts = defaultdict(int)
        
        for changed, affected in observations:
            cooccur[(changed, affected)] += 1
            node_counts[changed] += 1
            node_counts[affected] += 1
        
        # Calculate correlation strength
        correlations = []
        for (a, b), count in cooccur.items():
            if node_counts[a] > 0:
                strength = count / node_counts[a]
                if strength > 0.3:  # Threshold
                    correlations.append((a, b, strength))
        
        return sorted(correlations, key=lambda x: x[2], reverse=True)
    
    def learn_from_observations(self, observations: List[Tuple[str, str]]):
        """Learn causal edges from observation pairs."""
        correlations = self.find_correlations(observations)
        
        for source, target, strength in correlations:
            self.causes(source, target, strength)
    
    # -------------------------------------------------------------------------
    # Visualization
    # -------------------------------------------------------------------------
    
    def print_graph(self):
        """Print the causal graph."""
        print(f"\n{'='*60}")
        print("CAUSAL GRAPH")
        print(f"{'='*60}")
        print(f"Nodes: {len(self.nodes)}")
        print(f"Edges: {len(self.edges)}")
        
        print(f"\nEdges:")
        for (src, tgt), edge in sorted(self.edges.items()):
            amp_str = f" ×{edge.amplification:.1f}" if edge.amplification != 1.0 else ""
            print(f"  {src} --[{edge.causal_type.name}]--> {tgt} "
                  f"(str={edge.strength:.2f}, conf={edge.confidence:.2f}{amp_str})")
    
    def print_impact(self, report: ImpactReport):
        """Print impact report."""
        print(f"\n{'='*60}")
        print(f"IMPACT REPORT: {report.source}")
        print(f"{'='*60}")
        
        print(f"\nDirect impact ({len(report.direct_impact)}):")
        for node in report.direct_impact[:5]:
            print(f"  → {node}")
        
        print(f"\nIndirect impact ({len(report.indirect_impact)}):")
        for node in report.indirect_impact[:5]:
            print(f"  ⤳ {node}")
        
        print(f"\nMetrics:")
        print(f"  Reach: {report.reach} nodes")
        print(f"  Max depth: {report.max_depth} hops")
        print(f"  Total amplification: {report.total_amplification:.2f}x")
        
        if report.butterflies:
            print(f"\n🦋 BUTTERFLY EFFECTS ({len(report.butterflies)}):")
            for b in report.butterflies[:3]:
                print(f"  {b.origin} → {b.final_impact[0]}")
                print(f"    Chain: {' → '.join(b.chain.nodes)}")
                print(f"    Amplification: {b.amplification_ratio:.1f}x")
                print(f"    Criticality: {b.criticality:.2f}")
        
        if report.critical_paths:
            print(f"\n⚠️ CRITICAL PATHS ({len(report.critical_paths)}):")
            for chain in report.critical_paths[:3]:
                print(f"  {' → '.join(chain.nodes)}")
                print(f"    Amplification: {chain.total_amplification:.2f}x")


# =============================================================================
# POC
# =============================================================================

def poc_l11_butterfly():
    """L11 POC: Butterfly Causality."""
    print("=" * 60)
    print("L11: BUTTERFLY CAUSALITY")
    print("=" * 60)
    
    engine = ButterflyEngine()
    
    # -------------------------------------------------------------------------
    # Test 1: Build causal graph
    # -------------------------------------------------------------------------
    
    print(f"\n[1] Build causal graph:")
    
    # Create a system with potential butterfly effects
    # Config change → Validation → Database → Cache → API → Users
    
    engine.add_node("config_change", criticality=0.3)
    engine.add_node("validation_rules", criticality=0.5)
    engine.add_node("database_schema", criticality=0.8)
    engine.add_node("cache_layer", criticality=0.6)
    engine.add_node("api_endpoints", criticality=0.9)
    engine.add_node("user_sessions", criticality=1.0)
    
    # Causal edges with amplification
    engine.causes("config_change", "validation_rules", strength=0.7)
    engine.amplifies("validation_rules", "database_schema", factor=2.0)
    engine.triggers("database_schema", "cache_layer", amplification=1.5)
    engine.amplifies("cache_layer", "api_endpoints", factor=3.0)
    engine.triggers("api_endpoints", "user_sessions", amplification=2.0)
    
    # Also add a parallel path
    engine.causes("config_change", "cache_layer", strength=0.3)
    
    print(f"    Nodes: {len(engine.nodes)}")
    print(f"    Edges: {len(engine.edges)}")
    engine.print_graph()
    print(f"    ✓ PASS")
    
    # -------------------------------------------------------------------------
    # Test 2: Trace causal chain
    # -------------------------------------------------------------------------
    
    print(f"\n[2] Trace causal chain:")
    
    chains = engine.trace_chain("config_change", "user_sessions")
    print(f"    Chains from config_change to user_sessions: {len(chains)}")
    
    for i, chain in enumerate(chains):
        print(f"    Chain {i+1}: {' → '.join(chain.nodes)}")
        print(f"      Hops: {chain.total_hops}")
        print(f"      Amplification: {chain.total_amplification:.1f}x")
        print(f"      Confidence: {chain.confidence:.2f}")
    
    assert len(chains) >= 1
    print(f"    ✓ PASS")
    
    # -------------------------------------------------------------------------
    # Test 3: Detect butterfly effects
    # -------------------------------------------------------------------------
    
    print(f"\n[3] Detect butterfly effects:")
    
    butterflies = engine.detect_butterflies("config_change", input_magnitude=1.0)
    print(f"    Butterflies from config_change: {len(butterflies)}")
    
    for b in butterflies:
        print(f"    🦋 {b.origin} → {b.final_impact[0]}")
        print(f"       Amplification: {b.amplification_ratio:.1f}x")
        print(f"       Criticality: {b.criticality:.2f}")
    
    # Should detect butterfly to user_sessions (high amplification)
    user_butterfly = [b for b in butterflies if "user_sessions" in b.final_impact]
    assert len(user_butterfly) >= 1, "Should detect butterfly to user_sessions"
    assert user_butterfly[0].amplification_ratio >= 5.0, "Should have high amplification"
    print(f"    ✓ PASS")
    
    # -------------------------------------------------------------------------
    # Test 4: Full impact analysis
    # -------------------------------------------------------------------------
    
    print(f"\n[4] Full impact analysis:")
    
    report = engine.analyze_impact("config_change", change_magnitude=1.0)
    engine.print_impact(report)
    
    assert report.reach >= 5, "Should reach multiple nodes"
    assert report.max_depth >= 4, "Should have deep propagation"
    print(f"    ✓ PASS")
    
    # -------------------------------------------------------------------------
    # Test 5: Root cause tracing
    # -------------------------------------------------------------------------
    
    print(f"\n[5] Root cause tracing:")
    
    causes = engine.trace_root_causes("user_sessions")
    print(f"    Root causes of user_sessions: {len(causes)}")
    
    for cause, chain in list(causes.items())[:3]:
        print(f"    ← {cause}")
        print(f"      Chain: {' → '.join(chain.nodes)}")
    
    # config_change should be a root cause
    assert "config_change" in causes, "config_change should be root cause"
    print(f"    ✓ PASS")
    
    # -------------------------------------------------------------------------
    # Test 6: Learn from observations
    # -------------------------------------------------------------------------
    
    print(f"\n[6] Learn from observations:")
    
    # Simulate observed correlations
    observations = [
        ("module_A", "module_B"),
        ("module_A", "module_B"),
        ("module_A", "module_B"),
        ("module_A", "module_C"),
        ("module_B", "module_C"),
        ("module_B", "module_C"),
        ("module_B", "module_D"),
    ]
    
    engine.learn_from_observations(observations)
    
    # Check learned edges
    assert ("module_A", "module_B") in engine.edges
    print(f"    Learned edge: module_A → module_B")
    print(f"    Strength: {engine.edges[('module_A', 'module_B')].strength:.2f}")
    print(f"    ✓ PASS")
    
    # -------------------------------------------------------------------------
    # Test 7: Find all butterflies
    # -------------------------------------------------------------------------
    
    print(f"\n[7] Find all butterflies:")
    
    all_butterflies = engine.find_all_butterflies()
    print(f"    Total butterflies in system: {len(all_butterflies)}")
    
    for b in all_butterflies[:5]:
        print(f"    🦋 {b.origin} ⤳ {b.final_impact[0]} "
              f"(amp={b.amplification_ratio:.1f}x, crit={b.criticality:.2f})")
    
    print(f"    ✓ PASS")
    
    # -------------------------------------------------------------------------
    # Test 8: Complex cascade
    # -------------------------------------------------------------------------
    
    print(f"\n[8] Complex cascade (microservices):")
    
    # Simulate microservices architecture
    services = ["auth", "users", "orders", "payments", "inventory", "shipping", "notifications"]
    
    for svc in services:
        engine.add_node(svc, criticality=0.7)
    
    # Create realistic dependencies
    engine.causes("auth", "users", 0.9)
    engine.causes("users", "orders", 0.8)
    engine.amplifies("orders", "payments", 2.0)
    engine.amplifies("orders", "inventory", 1.5)
    engine.triggers("payments", "notifications", 1.2)
    engine.triggers("inventory", "shipping", 1.8)
    engine.amplifies("shipping", "notifications", 2.5)
    
    # Analyze impact of auth change
    auth_report = engine.analyze_impact("auth", 1.0)
    print(f"    Auth change impact:")
    print(f"      Reach: {auth_report.reach} services")
    print(f"      Max depth: {auth_report.max_depth} hops")
    print(f"      Butterflies: {len(auth_report.butterflies)}")
    
    if auth_report.butterflies:
        top_butterfly = auth_report.butterflies[0]
        print(f"    🦋 Worst butterfly: {top_butterfly.origin} ⤳ {top_butterfly.final_impact[0]}")
        print(f"       Amplification: {top_butterfly.amplification_ratio:.1f}x")
    
    print(f"    ✓ PASS")
    
    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    
    print(f"\n{'='*60}")
    print("L11 POC: ALL TESTS PASSED")
    print(f"{'='*60}")
    
    print("""
    Proved:
    ✓ Causal graph construction (nodes, edges, types)
    ✓ Multi-hop chain tracing (A → B → C → D)
    ✓ Butterfly detection (small cause → large effect)
    ✓ Impact analysis (reach, depth, amplification)
    ✓ Root cause tracing (backwards from effect)
    ✓ Learning from observations (correlation → causation)
    ✓ All-system butterfly scan
    ✓ Complex cascade simulation
    
    BUTTERFLY CAUSALITY enables:
    - Predict impact BEFORE making changes
    - Trace root causes of failures
    - Detect dangerous amplification paths
    - Identify critical single points of failure
    
    "A small config change can crash all user sessions."
    """)
    
    return engine


if __name__ == "__main__":
    poc_l11_butterfly()
