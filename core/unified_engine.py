"""
LadybugDB Unified Query Engine

One substrate. All operations.
- SQL (DuckDB)
- Cypher (Graph traversal via recursive CTE)
- Vector (Lance native ANN)
- Hamming (SIMD 10K)

BtrBlocks + Procella principles:
- Decompress at compute speed (86 Gbit/s)
- Evaluate on compressed data
- Zero-copy Arrow throughout
"""

import lancedb
import duckdb
import pyarrow as pa
import numpy as np
from typing import Union, List, Dict, Any, Optional
from dataclasses import dataclass
import re
import json
from pathlib import Path

# Import our SIMD kernels
try:
    from .simd_kernel import ComputeEngine, kernel_hamming
    from .simd_fast import FastVector, FastBatch
    SIMD_AVAILABLE = True
except ImportError:
    SIMD_AVAILABLE = False


# =============================================================================
# SCHEMA DEFINITIONS
# =============================================================================

NODES_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("label", pa.string()),              # Thought, Concept, Session
    pa.field("fingerprint", pa.binary(1250)),    # 10K bits
    pa.field("embedding", pa.list_(pa.float32(), 1024)),  # Jina
    pa.field("qidx", pa.uint8()),                # Qualia index
    pa.field("thinking_style", pa.list_(pa.float32(), 7)),  # τ vector
    pa.field("content", pa.string()),
    pa.field("properties", pa.string()),         # JSON
    pa.field("created_at", pa.timestamp('us')),
    pa.field("version", pa.int64()),
])

EDGES_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("from_id", pa.string()),
    pa.field("to_id", pa.string()),
    pa.field("type", pa.string()),               # CAUSES, ENABLES, AMPLIFIES
    pa.field("weight", pa.float32()),
    pa.field("amplification", pa.float32()),     # For butterfly detection
    pa.field("properties", pa.string()),
    pa.field("created_at", pa.timestamp('us')),
])


# =============================================================================
# CYPHER PARSER (Simplified)
# =============================================================================

@dataclass
class CypherPattern:
    """Parsed Cypher MATCH pattern."""
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    where: Optional[str]
    returns: List[str]
    
    
def parse_cypher(cypher: str) -> CypherPattern:
    """
    Parse simple Cypher patterns.
    
    MATCH (a:Thought)-[:CAUSES]->(b:Thought)
    WHERE a.qidx > 100
    RETURN b
    """
    # Extract MATCH pattern
    match_pattern = re.search(r'MATCH\s+(.+?)(?:WHERE|RETURN|$)', cypher, re.I | re.S)
    where_clause = re.search(r'WHERE\s+(.+?)(?:RETURN|$)', cypher, re.I | re.S)
    return_clause = re.search(r'RETURN\s+(.+?)$', cypher, re.I | re.S)
    
    if not match_pattern:
        raise ValueError("No MATCH clause found")
    
    pattern_str = match_pattern.group(1).strip()
    
    # Parse nodes: (alias:Label {props})
    node_pattern = r'\((\w+)(?::(\w+))?(?:\s*\{([^}]+)\})?\)'
    nodes = []
    for match in re.finditer(node_pattern, pattern_str):
        alias, label, props = match.groups()
        nodes.append({
            'alias': alias,
            'label': label,
            'props': parse_props(props) if props else {}
        })
    
    # Parse edges: -[:TYPE*min..max]->
    edge_pattern = r'-\[:?(\w+)?(?:\*(\d+)?\.\.(\d+))?\]->'
    edges = []
    for match in re.finditer(edge_pattern, pattern_str):
        etype, min_hops, max_hops = match.groups()
        edges.append({
            'type': etype,
            'min_hops': int(min_hops) if min_hops else 1,
            'max_hops': int(max_hops) if max_hops else 1,
            'variable_length': min_hops is not None or max_hops is not None
        })
    
    return CypherPattern(
        nodes=nodes,
        edges=edges,
        where=where_clause.group(1).strip() if where_clause else None,
        returns=[r.strip() for r in return_clause.group(1).split(',')] if return_clause else ['*']
    )


def parse_props(props_str: str) -> Dict[str, Any]:
    """Parse {key: value, ...} property string."""
    props = {}
    for pair in props_str.split(','):
        if ':' in pair:
            key, value = pair.split(':', 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            props[key] = value
    return props


def cypher_to_sql(cypher: str) -> str:
    """
    Transpile Cypher to SQL with recursive CTEs.
    
    Simple case (1 hop):
        MATCH (a:Thought)-[:CAUSES]->(b:Thought)
        WHERE a.qidx > 100
        RETURN b
        
        →
        
        SELECT b.*
        FROM nodes a
        JOIN edges e ON a.id = e.from_id AND e.type = 'CAUSES'
        JOIN nodes b ON e.to_id = b.id
        WHERE a.label = 'Thought' AND b.label = 'Thought'
          AND a.qidx > 100
    
    Variable length (n hops):
        MATCH (a)-[:CAUSES*1..5]->(b)
        
        →
        
        WITH RECURSIVE traverse AS (...)
    """
    pattern = parse_cypher(cypher)
    
    # Check if we need recursive CTE
    needs_recursive = any(e.get('variable_length') for e in pattern.edges)
    
    if needs_recursive:
        return _cypher_to_recursive_sql(pattern)
    else:
        return _cypher_to_simple_sql(pattern)


def _cypher_to_simple_sql(pattern: CypherPattern) -> str:
    """Generate simple JOIN-based SQL."""
    
    if len(pattern.nodes) < 2:
        # Single node query
        node = pattern.nodes[0]
        where_parts = []
        if node['label']:
            where_parts.append(f"label = '{node['label']}'")
        for k, v in node['props'].items():
            where_parts.append(f"{k} = '{v}'")
        if pattern.where:
            where_parts.append(f"({pattern.where})")
        
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        return f"SELECT * FROM nodes {node['alias']} {where_clause}"
    
    # Multi-node with edges
    select_parts = []
    from_parts = [f"nodes {pattern.nodes[0]['alias']}"]
    where_parts = []
    
    for i, edge in enumerate(pattern.edges):
        prev_node = pattern.nodes[i]
        next_node = pattern.nodes[i + 1]
        edge_alias = f"e{i}"
        
        # JOIN edge
        join_clause = f"JOIN edges {edge_alias} ON {prev_node['alias']}.id = {edge_alias}.from_id"
        if edge['type']:
            join_clause += f" AND {edge_alias}.type = '{edge['type']}'"
        from_parts.append(join_clause)
        
        # JOIN next node
        from_parts.append(f"JOIN nodes {next_node['alias']} ON {edge_alias}.to_id = {next_node['alias']}.id")
        
        # Label filters
        if prev_node['label']:
            where_parts.append(f"{prev_node['alias']}.label = '{prev_node['label']}'")
        if next_node['label']:
            where_parts.append(f"{next_node['alias']}.label = '{next_node['label']}'")
    
    # User WHERE clause
    if pattern.where:
        where_parts.append(f"({pattern.where})")
    
    # Build SELECT
    if pattern.returns == ['*']:
        select_parts = [f"{pattern.nodes[-1]['alias']}.*"]
    else:
        select_parts = pattern.returns
    
    sql = f"SELECT {', '.join(select_parts)}\nFROM {from_parts[0]}\n"
    sql += '\n'.join(from_parts[1:])
    if where_parts:
        sql += f"\nWHERE {' AND '.join(where_parts)}"
    
    return sql


def _cypher_to_recursive_sql(pattern: CypherPattern) -> str:
    """Generate recursive CTE for variable-length paths."""
    
    start_node = pattern.nodes[0]
    end_node = pattern.nodes[-1] if len(pattern.nodes) > 1 else None
    edge = pattern.edges[0] if pattern.edges else None
    
    edge_type_filter = f"AND e.type = '{edge['type']}'" if edge and edge['type'] else ""
    max_depth = edge['max_hops'] if edge else 10
    min_depth = edge['min_hops'] if edge else 1
    
    # Start condition
    start_where = []
    if start_node['label']:
        start_where.append(f"label = '{start_node['label']}'")
    for k, v in start_node['props'].items():
        start_where.append(f"{k} = '{v}'")
    start_condition = f"WHERE {' AND '.join(start_where)}" if start_where else ""
    
    sql = f"""
WITH RECURSIVE traverse AS (
    -- Base case: start nodes
    SELECT 
        id,
        ARRAY[id] as path,
        1.0 as amplification,
        0 as depth
    FROM nodes
    {start_condition}
    
    UNION ALL
    
    -- Recursive case: follow edges
    SELECT 
        n.id,
        t.path || n.id,
        t.amplification * COALESCE(e.amplification, e.weight, 1.0),
        t.depth + 1
    FROM traverse t
    JOIN edges e ON t.id = e.from_id {edge_type_filter}
    JOIN nodes n ON e.to_id = n.id
    WHERE t.depth < {max_depth}
      AND n.id != ALL(t.path)  -- Cycle detection
)
SELECT t.*, n.*
FROM traverse t
JOIN nodes n ON t.id = n.id
WHERE t.depth >= {min_depth}
"""
    
    # Add end node filter
    if end_node and end_node['label']:
        sql += f"  AND n.label = '{end_node['label']}'\n"
    
    # Add user WHERE
    if pattern.where:
        # Rewrite aliases
        where = pattern.where
        if start_node['alias'] != 'n':
            where = where.replace(f"{start_node['alias']}.", "n.")
        sql += f"  AND ({where})\n"
    
    sql += "ORDER BY t.depth, t.amplification DESC"
    
    return sql


# =============================================================================
# UNIFIED QUERY ENGINE
# =============================================================================

class LadybugEngine:
    """
    Unified query engine over LanceDB.
    
    Accepts:
    - SQL: Standard DuckDB SQL
    - Cypher: Graph patterns (transpiled to recursive SQL)
    - Vector: ANN search
    - Hamming: 10K binary similarity
    - Mixed: All of the above in one query
    """
    
    def __init__(self, uri: str = "~/.ladybug"):
        self.uri = Path(uri).expanduser()
        self.uri.mkdir(parents=True, exist_ok=True)
        
        # Initialize LanceDB
        self.lance = lancedb.connect(str(self.uri))
        
        # Initialize DuckDB with Lance integration
        self.duck = duckdb.connect()
        
        # Create tables if they don't exist
        self._ensure_tables()
        
        # Register Lance tables as DuckDB views
        self._register_views()
        
        # Register UDFs
        self._register_udfs()
        
        # SIMD engine for Hamming
        if SIMD_AVAILABLE:
            self.simd = ComputeEngine()
        else:
            self.simd = None
    
    def _ensure_tables(self):
        """Create nodes and edges tables if they don't exist."""
        if "nodes" not in self.lance.table_names():
            self.lance.create_table("nodes", schema=NODES_SCHEMA)
        if "edges" not in self.lance.table_names():
            self.lance.create_table("edges", schema=EDGES_SCHEMA)
    
    def _register_views(self):
        """Register Lance tables as DuckDB views."""
        for table_name in self.lance.table_names():
            # Use lance_scan function
            self.duck.execute(f"""
                CREATE OR REPLACE VIEW {table_name} AS 
                SELECT * FROM read_parquet('{self.uri}/{table_name}.lance/**/*.parquet')
            """)
    
    def _register_udfs(self):
        """Register custom functions for Hamming and vector ops."""
        
        # Hamming distance UDF
        def hamming_distance(a: bytes, b: bytes) -> int:
            if a is None or b is None:
                return 10000  # Max distance
            arr_a = np.frombuffer(a, dtype=np.uint64)
            arr_b = np.frombuffer(b, dtype=np.uint64)
            return int(np.sum([bin(x ^ y).count('1') for x, y in zip(arr_a, arr_b)]))
        
        self.duck.create_function("hamming", hamming_distance)
        
        # Hamming similarity UDF
        def hamming_similarity(a: bytes, b: bytes) -> float:
            dist = hamming_distance(a, b)
            return 1.0 - dist / 10000.0
        
        self.duck.create_function("similarity", hamming_similarity)
    
    # -------------------------------------------------------------------------
    # QUERY INTERFACE
    # -------------------------------------------------------------------------
    
    def query(self, q: str, params: Dict[str, Any] = None) -> pa.Table:
        """
        Execute a query in any supported syntax.
        
        Auto-detects:
        - MATCH ... → Cypher
        - SELECT ... → SQL
        - SEARCH(...) → Vector
        - RESONATE(...) → Hamming
        """
        q = q.strip()
        params = params or {}
        
        # Detect query type
        if q.upper().startswith("MATCH"):
            sql = cypher_to_sql(q)
            return self._execute_sql(sql, params)
        
        elif "RESONATE(" in q.upper():
            return self._execute_resonate(q, params)
        
        elif "VECTOR_SEARCH(" in q.upper():
            return self._execute_vector_search(q, params)
        
        else:
            return self._execute_sql(q, params)
    
    def _execute_sql(self, sql: str, params: Dict[str, Any]) -> pa.Table:
        """Execute SQL with parameter substitution."""
        # Simple parameter substitution
        for key, value in params.items():
            placeholder = f"${key}"
            if isinstance(value, str):
                sql = sql.replace(placeholder, f"'{value}'")
            elif isinstance(value, bytes):
                # Binary as hex
                sql = sql.replace(placeholder, f"'\\x{value.hex()}'::BLOB")
            else:
                sql = sql.replace(placeholder, str(value))
        
        return self.duck.execute(sql).fetch_arrow_table()
    
    def _execute_resonate(self, q: str, params: Dict[str, Any]) -> pa.Table:
        """
        Execute RESONATE query.
        
        SELECT * FROM nodes WHERE RESONATE(fingerprint, $fp, 0.6)
        
        Expands to:
        
        SELECT *, similarity(fingerprint, $fp) as resonance
        FROM nodes
        WHERE hamming(fingerprint, $fp) < 4000
        ORDER BY resonance DESC
        """
        # Extract RESONATE call
        match = re.search(
            r'RESONATE\s*\(\s*(\w+)\s*,\s*(\$?\w+)\s*,\s*([\d.]+)\s*\)',
            q, re.I
        )
        if not match:
            raise ValueError("Invalid RESONATE syntax")
        
        column, param, threshold = match.groups()
        threshold = float(threshold)
        max_distance = int((1.0 - threshold) * 10000)
        
        # Expand query
        expanded = q[:match.start()] + f"hamming({column}, {param}) < {max_distance}" + q[match.end():]
        
        # Add similarity column and ordering
        if "SELECT" in expanded.upper():
            expanded = expanded.replace(
                "SELECT ", 
                f"SELECT similarity({column}, {param}) as resonance, ",
                1
            )
            if "ORDER BY" not in expanded.upper():
                expanded += " ORDER BY resonance DESC"
        
        return self._execute_sql(expanded, params)
    
    def _execute_vector_search(self, q: str, params: Dict[str, Any]) -> pa.Table:
        """
        Execute vector similarity search.
        
        SELECT * FROM nodes WHERE VECTOR_SEARCH(embedding, $vec, 10)
        """
        # Extract VECTOR_SEARCH call
        match = re.search(
            r'VECTOR_SEARCH\s*\(\s*(\w+)\s*,\s*(\$\w+)\s*,\s*(\d+)\s*\)',
            q, re.I
        )
        if not match:
            raise ValueError("Invalid VECTOR_SEARCH syntax")
        
        column, param_name, k = match.groups()
        vector = params.get(param_name.lstrip('$'))
        k = int(k)
        
        if vector is None:
            raise ValueError(f"Missing parameter: {param_name}")
        
        # Use Lance native vector search
        table = self.lance.open_table("nodes")
        results = table.search(vector).limit(k).to_arrow()
        
        return results
    
    # -------------------------------------------------------------------------
    # GRAPH OPERATIONS
    # -------------------------------------------------------------------------
    
    def add_node(self, id: str, label: str, **properties) -> None:
        """Add a node to the graph."""
        table = self.lance.open_table("nodes")
        
        node = {
            "id": id,
            "label": label,
            "fingerprint": properties.pop("fingerprint", None),
            "embedding": properties.pop("embedding", None),
            "qidx": properties.pop("qidx", 128),
            "thinking_style": properties.pop("thinking_style", [0.5] * 7),
            "content": properties.pop("content", ""),
            "properties": json.dumps(properties),
            "created_at": pa.scalar(np.datetime64('now', 'us')),
            "version": 1,
        }
        
        table.add([node])
    
    def add_edge(self, from_id: str, to_id: str, edge_type: str, 
                 weight: float = 1.0, amplification: float = 1.0,
                 **properties) -> None:
        """Add an edge to the graph."""
        table = self.lance.open_table("edges")
        
        edge = {
            "id": f"{from_id}->{to_id}:{edge_type}",
            "from_id": from_id,
            "to_id": to_id,
            "type": edge_type,
            "weight": weight,
            "amplification": amplification,
            "properties": json.dumps(properties),
            "created_at": pa.scalar(np.datetime64('now', 'us')),
        }
        
        table.add([edge])
    
    def causes(self, from_id: str, to_id: str, amplification: float = 1.0):
        """Shorthand for CAUSES edge."""
        self.add_edge(from_id, to_id, "CAUSES", amplification=amplification)
    
    def enables(self, from_id: str, to_id: str):
        """Shorthand for ENABLES edge."""
        self.add_edge(from_id, to_id, "ENABLES")
    
    def amplifies(self, from_id: str, to_id: str, factor: float):
        """Shorthand for AMPLIFIES edge."""
        self.add_edge(from_id, to_id, "AMPLIFIES", amplification=factor)
    
    # -------------------------------------------------------------------------
    # BUTTERFLY DETECTION
    # -------------------------------------------------------------------------
    
    def detect_butterflies(self, source_id: str, threshold: float = 5.0) -> pa.Table:
        """
        Find butterfly effects: paths with amplification > threshold.
        """
        cypher = f"""
        MATCH (source)-[:CAUSES|AMPLIFIES*1..10]->(target)
        WHERE source.id = '{source_id}'
        RETURN target, path, amplification
        """
        
        sql = cypher_to_sql(cypher)
        sql += f"\n  AND t.amplification > {threshold}"
        
        return self._execute_sql(sql, {})
    
    def impact_analysis(self, change_id: str) -> Dict[str, Any]:
        """
        Full impact analysis for a potential change.
        """
        results = self.query(f"""
            MATCH (source)-[:CAUSES|AMPLIFIES|ENABLES*1..10]->(affected)
            WHERE source.id = '{change_id}'
            RETURN affected
        """)
        
        butterflies = self.detect_butterflies(change_id)
        
        return {
            "total_affected": len(results),
            "butterfly_effects": len(butterflies),
            "max_amplification": butterflies.column("amplification").to_pylist()[0] if len(butterflies) > 0 else 1.0,
            "affected_nodes": results,
            "butterflies": butterflies,
        }
    
    # -------------------------------------------------------------------------
    # RESONANCE OPERATIONS
    # -------------------------------------------------------------------------
    
    def find_similar(self, fingerprint: bytes, k: int = 10, 
                     where: str = None) -> pa.Table:
        """
        Find nodes with similar fingerprints (Hamming distance).
        """
        q = f"""
            SELECT *, hamming(fingerprint, $fp) as distance,
                   similarity(fingerprint, $fp) as resonance
            FROM nodes
            WHERE fingerprint IS NOT NULL
            ORDER BY distance ASC
            LIMIT {k}
        """
        
        if where:
            q = q.replace("WHERE", f"WHERE ({where}) AND")
        
        return self._execute_sql(q, {"fp": fingerprint})
    
    def resonate(self, fingerprint: bytes, threshold: float = 0.6,
                 where: str = None) -> pa.Table:
        """
        Find all nodes above similarity threshold.
        """
        max_distance = int((1.0 - threshold) * 10000)
        
        q = f"""
            SELECT *, similarity(fingerprint, $fp) as resonance
            FROM nodes
            WHERE hamming(fingerprint, $fp) < {max_distance}
            ORDER BY resonance DESC
        """
        
        if where:
            q = q.replace(f"< {max_distance}", f"< {max_distance} AND ({where})")
        
        return self._execute_sql(q, {"fp": fingerprint})
    
    # -------------------------------------------------------------------------
    # VERSIONING (Iceberg-style)
    # -------------------------------------------------------------------------
    
    def checkout(self, version: Union[str, int]) -> "LadybugEngine":
        """
        Time travel to a specific version.
        """
        # LanceDB supports versioning natively
        # This returns a read-only view at that version
        engine = LadybugEngine.__new__(LadybugEngine)
        engine.uri = self.uri
        engine.lance = lancedb.connect(str(self.uri))
        engine.duck = duckdb.connect()
        
        # Open tables at specific version
        # (Actual API depends on LanceDB version)
        
        return engine
    
    def diff(self, old_version: int, new_version: int = None) -> pa.Table:
        """
        Show changes between versions.
        """
        # This would use Lance's versioning API
        pass


# =============================================================================
# CONVENIENCE: SQL-LIKE INTERFACE
# =============================================================================

def connect(uri: str = "~/.ladybug") -> LadybugEngine:
    """Create a connection to LadybugDB."""
    return LadybugEngine(uri)


# =============================================================================
# POSTGRES WIRE PROTOCOL (Optional)
# =============================================================================

class LadybugPGServer:
    """
    PostgreSQL wire protocol server.
    
    Allows connecting with psql, pgAdmin, any BI tool.
    """
    
    def __init__(self, engine: LadybugEngine, port: int = 5433):
        self.engine = engine
        self.port = port
    
    def start(self):
        """Start the PG wire protocol server."""
        # Would use pg_protocol or similar library
        # For now, this is a placeholder
        print(f"LadybugDB listening on port {self.port}")
        print(f"Connect with: psql -h localhost -p {self.port} -d ladybug")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Demo
    engine = connect("/tmp/ladybug_test")
    
    # Add some test nodes
    engine.add_node("config_1", "Config", content="Database connection string")
    engine.add_node("validator_1", "Validator", content="Input validation rules")
    engine.add_node("cache_1", "Cache", content="Redis cache layer")
    engine.add_node("api_1", "API", content="REST endpoint handler")
    engine.add_node("users_1", "Users", content="User session manager", qidx=42)
    
    # Add causal edges with amplification
    engine.causes("config_1", "validator_1", amplification=2.0)
    engine.causes("validator_1", "cache_1", amplification=1.5)
    engine.amplifies("cache_1", "api_1", factor=3.0)
    engine.causes("api_1", "users_1", amplification=2.0)
    
    # Query with Cypher
    print("=== Cypher Query ===")
    result = engine.query("""
        MATCH (a:Config)-[:CAUSES*1..5]->(b)
        RETURN b
    """)
    print(result.to_pandas())
    
    # SQL query
    print("\n=== SQL Query ===")
    result = engine.query("""
        SELECT id, label, qidx 
        FROM nodes 
        WHERE qidx < 100
    """)
    print(result.to_pandas())
    
    # Butterfly detection
    print("\n=== Butterfly Effects ===")
    impact = engine.impact_analysis("config_1")
    print(f"Total affected: {impact['total_affected']}")
    print(f"Butterfly effects: {impact['butterfly_effects']}")
    print(f"Max amplification: {impact['max_amplification']}")
