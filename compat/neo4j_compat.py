"""
LadybugDB Neo4j-Compatible Driver

Familiar Neo4j driver syntax, backed by recursive CTEs.

Usage (feels like Neo4j):
    from ladybugdb.compat import GraphDatabase
    
    driver = GraphDatabase.driver("ladybug://./mydb")
    
    with driver.session() as session:
        # Cypher queries work!
        result = session.run('''
            MATCH (a:Thought)-[:CAUSES*1..5]->(b:Thought)
            WHERE a.qidx > 100
            RETURN b
        ''')
        
        for record in result:
            print(record['b'])

But underneath: DuckDB recursive CTEs, not actual Neo4j.
"""

from __future__ import annotations
import re
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union, Iterator, Tuple
from datetime import datetime
from contextlib import contextmanager
import json

from .dto import Node, Edge, SearchResult, PathResult


# =============================================================================
# CYPHER PARSER
# =============================================================================

@dataclass
class CypherPattern:
    """Parsed Cypher MATCH pattern."""
    nodes: List[Dict[str, Any]]  # [{var, label, props}]
    edges: List[Dict[str, Any]]  # [{var, type, direction, min_hops, max_hops}]
    
    @property
    def is_variable_length(self) -> bool:
        """Check if any edge has variable length."""
        return any(e.get('max_hops', 1) > 1 for e in self.edges)


class CypherParser:
    """
    Parse Cypher queries into AST components.
    
    Supports:
    - MATCH (a:Label)-[:TYPE]->(b:Label)
    - MATCH (a)-[:TYPE*1..5]->(b)  # Variable length
    - WHERE a.prop = value
    - RETURN a, b.prop AS alias
    - ORDER BY, LIMIT, SKIP
    """
    
    # Regex patterns
    NODE_PATTERN = re.compile(
        r'\((\w+)?(?::(\w+))?(?:\s*\{([^}]+)\})?\)'
    )
    EDGE_PATTERN = re.compile(
        r'-\[(\w+)?(?::(\w+))?(?:\*(\d+)?\.\.(\d+)?)?\]->'
    )
    EDGE_PATTERN_UNDIRECTED = re.compile(
        r'-\[(\w+)?(?::(\w+))?(?:\*(\d+)?\.\.(\d+)?)?\]-'
    )
    
    @classmethod
    def parse(cls, cypher: str) -> Dict[str, Any]:
        """Parse Cypher query into components."""
        result = {
            'type': 'UNKNOWN',
            'match': None,
            'where': None,
            'return': None,
            'order_by': None,
            'limit': None,
            'skip': None,
            'create': None,
            'merge': None,
            'delete': None,
            'set': None,
        }
        
        # Normalize whitespace
        cypher = ' '.join(cypher.split())
        
        # Detect query type
        cypher_upper = cypher.upper()
        if cypher_upper.startswith('MATCH'):
            result['type'] = 'MATCH'
        elif cypher_upper.startswith('CREATE'):
            result['type'] = 'CREATE'
        elif cypher_upper.startswith('MERGE'):
            result['type'] = 'MERGE'
        
        # Parse MATCH clause
        match_match = re.search(r'MATCH\s+(.+?)(?=WHERE|RETURN|ORDER|LIMIT|$)', cypher, re.I)
        if match_match:
            result['match'] = cls._parse_match_pattern(match_match.group(1))
        
        # Parse WHERE clause
        where_match = re.search(r'WHERE\s+(.+?)(?=RETURN|ORDER|LIMIT|$)', cypher, re.I)
        if where_match:
            result['where'] = cls._parse_where(where_match.group(1))
        
        # Parse RETURN clause
        return_match = re.search(r'RETURN\s+(.+?)(?=ORDER|LIMIT|$)', cypher, re.I)
        if return_match:
            result['return'] = cls._parse_return(return_match.group(1))
        
        # Parse ORDER BY
        order_match = re.search(r'ORDER\s+BY\s+(.+?)(?=LIMIT|SKIP|$)', cypher, re.I)
        if order_match:
            result['order_by'] = cls._parse_order_by(order_match.group(1))
        
        # Parse LIMIT
        limit_match = re.search(r'LIMIT\s+(\d+)', cypher, re.I)
        if limit_match:
            result['limit'] = int(limit_match.group(1))
        
        # Parse SKIP
        skip_match = re.search(r'SKIP\s+(\d+)', cypher, re.I)
        if skip_match:
            result['skip'] = int(skip_match.group(1))
        
        return result
    
    @classmethod
    def _parse_match_pattern(cls, pattern: str) -> CypherPattern:
        """Parse MATCH pattern into nodes and edges."""
        nodes = []
        edges = []
        
        # Find all nodes
        for match in cls.NODE_PATTERN.finditer(pattern):
            var, label, props = match.groups()
            node = {
                'var': var or f'_n{len(nodes)}',
                'label': label,
                'props': cls._parse_props(props) if props else {},
            }
            nodes.append(node)
        
        # Find all edges
        for match in cls.EDGE_PATTERN.finditer(pattern):
            var, edge_type, min_hops, max_hops = match.groups()
            edge = {
                'var': var or f'_e{len(edges)}',
                'type': edge_type,
                'direction': 'OUT',
                'min_hops': int(min_hops) if min_hops else 1,
                'max_hops': int(max_hops) if max_hops else 1,
            }
            edges.append(edge)
        
        # Undirected edges
        for match in cls.EDGE_PATTERN_UNDIRECTED.finditer(pattern):
            var, edge_type, min_hops, max_hops = match.groups()
            edge = {
                'var': var or f'_e{len(edges)}',
                'type': edge_type,
                'direction': 'BOTH',
                'min_hops': int(min_hops) if min_hops else 1,
                'max_hops': int(max_hops) if max_hops else 1,
            }
            edges.append(edge)
        
        return CypherPattern(nodes=nodes, edges=edges)
    
    @classmethod
    def _parse_props(cls, props_str: str) -> Dict[str, Any]:
        """Parse property string like 'name: "foo", age: 42'."""
        props = {}
        for part in props_str.split(','):
            if ':' in part:
                key, value = part.split(':', 1)
                key = key.strip()
                value = value.strip().strip('"\'')
                # Try to parse as number
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
                props[key] = value
        return props
    
    @classmethod
    def _parse_where(cls, where_str: str) -> List[Dict[str, Any]]:
        """Parse WHERE conditions."""
        conditions = []
        # Simple parsing - split by AND
        parts = re.split(r'\s+AND\s+', where_str, flags=re.I)
        for part in parts:
            part = part.strip()
            # Parse comparison
            for op in ['>=', '<=', '!=', '<>', '=', '>', '<', 'CONTAINS', 'STARTS WITH', 'ENDS WITH']:
                if op in part.upper():
                    left, right = re.split(rf'\s*{op}\s*', part, maxsplit=1, flags=re.I)
                    conditions.append({
                        'left': left.strip(),
                        'op': op.upper().replace('<>', '!='),
                        'right': right.strip().strip('"\''),
                    })
                    break
        return conditions
    
    @classmethod
    def _parse_return(cls, return_str: str) -> List[Dict[str, Any]]:
        """Parse RETURN clause."""
        items = []
        for part in return_str.split(','):
            part = part.strip()
            # Check for alias
            alias_match = re.match(r'(.+?)\s+AS\s+(\w+)', part, re.I)
            if alias_match:
                items.append({
                    'expr': alias_match.group(1).strip(),
                    'alias': alias_match.group(2),
                })
            else:
                items.append({
                    'expr': part,
                    'alias': part.replace('.', '_'),
                })
        return items
    
    @classmethod
    def _parse_order_by(cls, order_str: str) -> List[Dict[str, Any]]:
        """Parse ORDER BY clause."""
        items = []
        for part in order_str.split(','):
            part = part.strip()
            desc = 'DESC' in part.upper()
            expr = re.sub(r'\s+(ASC|DESC)\s*$', '', part, flags=re.I).strip()
            items.append({
                'expr': expr,
                'desc': desc,
            })
        return items


# =============================================================================
# CYPHER TO SQL TRANSPILER
# =============================================================================

class CypherTranspiler:
    """
    Transpile Cypher to DuckDB SQL.
    
    Simple patterns → JOINs
    Variable-length → Recursive CTEs
    """
    
    @classmethod
    def transpile(cls, cypher: str) -> str:
        """Transpile Cypher query to SQL."""
        parsed = CypherParser.parse(cypher)
        
        if parsed['type'] == 'MATCH':
            return cls._transpile_match(parsed)
        elif parsed['type'] == 'CREATE':
            return cls._transpile_create(parsed)
        else:
            raise ValueError(f"Unsupported query type: {parsed['type']}")
    
    @classmethod
    def _transpile_match(cls, parsed: Dict[str, Any]) -> str:
        """Transpile MATCH query."""
        pattern = parsed['match']
        
        if pattern.is_variable_length:
            return cls._transpile_variable_length(parsed)
        else:
            return cls._transpile_simple_match(parsed)
    
    @classmethod
    def _transpile_simple_match(cls, parsed: Dict[str, Any]) -> str:
        """Transpile simple (non-variable-length) MATCH."""
        pattern = parsed['match']
        nodes = pattern.nodes
        edges = pattern.edges
        
        # Build FROM clause
        from_parts = []
        for i, node in enumerate(nodes):
            alias = node['var']
            from_parts.append(f"nodes {alias}")
        
        # Build JOIN conditions
        join_conditions = []
        for i, edge in enumerate(edges):
            if i < len(nodes) - 1:
                src = nodes[i]['var']
                dst = nodes[i + 1]['var']
                edge_alias = edge['var']
                
                from_parts.append(f"edges {edge_alias}")
                join_conditions.append(f"{src}.id = {edge_alias}.from_id")
                join_conditions.append(f"{dst}.id = {edge_alias}.to_id")
                
                if edge['type']:
                    join_conditions.append(f"{edge_alias}.type = '{edge['type']}'")
        
        # Add label filters
        for node in nodes:
            if node['label']:
                join_conditions.append(f"{node['var']}.label = '{node['label']}'")
        
        # Add WHERE conditions
        if parsed['where']:
            for cond in parsed['where']:
                left = cond['left']
                op = '=' if cond['op'] == '=' else cond['op']
                right = cond['right']
                
                # Quote string values
                try:
                    float(right)
                except ValueError:
                    right = f"'{right}'"
                
                join_conditions.append(f"{left} {op} {right}")
        
        # Build SELECT clause
        if parsed['return']:
            select_parts = []
            for item in parsed['return']:
                expr = item['expr']
                alias = item['alias']
                if expr == alias:
                    select_parts.append(f"{expr}.*" if '.' not in expr else expr)
                else:
                    select_parts.append(f"{expr} AS {alias}")
            select_clause = ', '.join(select_parts)
        else:
            select_clause = '*'
        
        # Build SQL
        sql = f"SELECT {select_clause}\nFROM {', '.join(from_parts)}"
        if join_conditions:
            sql += f"\nWHERE {' AND '.join(join_conditions)}"
        
        # ORDER BY
        if parsed['order_by']:
            order_parts = []
            for item in parsed['order_by']:
                order_parts.append(f"{item['expr']} {'DESC' if item['desc'] else 'ASC'}")
            sql += f"\nORDER BY {', '.join(order_parts)}"
        
        # LIMIT
        if parsed['limit']:
            sql += f"\nLIMIT {parsed['limit']}"
        
        # SKIP (OFFSET)
        if parsed['skip']:
            sql += f"\nOFFSET {parsed['skip']}"
        
        return sql
    
    @classmethod
    def _transpile_variable_length(cls, parsed: Dict[str, Any]) -> str:
        """Transpile variable-length path query using recursive CTE."""
        pattern = parsed['match']
        nodes = pattern.nodes
        edges = pattern.edges
        
        if len(nodes) < 2 or len(edges) < 1:
            raise ValueError("Variable-length path needs at least 2 nodes and 1 edge")
        
        src_node = nodes[0]
        dst_node = nodes[-1]
        edge = edges[0]  # Assume first edge has variable length
        
        min_hops = edge['min_hops']
        max_hops = edge['max_hops']
        edge_type = edge['type']
        
        # Build WHERE conditions for source
        src_conditions = []
        if src_node['label']:
            src_conditions.append(f"n.label = '{src_node['label']}'")
        
        if parsed['where']:
            for cond in parsed['where']:
                if cond['left'].startswith(src_node['var'] + '.'):
                    prop = cond['left'].split('.', 1)[1]
                    right = cond['right']
                    try:
                        float(right)
                    except ValueError:
                        right = f"'{right}'"
                    src_conditions.append(f"n.{prop} {cond['op']} {right}")
        
        src_where = ' AND '.join(src_conditions) if src_conditions else '1=1'
        
        # Build edge type filter
        edge_filter = f"e.type = '{edge_type}'" if edge_type else '1=1'
        
        # Build target label filter
        target_filter = f"n.label = '{dst_node['label']}'" if dst_node['label'] else '1=1'
        
        # Build recursive CTE
        sql = f"""
WITH RECURSIVE traverse AS (
    -- Base case: start from source nodes
    SELECT 
        n.id,
        ARRAY[n.id] AS path,
        1.0 AS amplification,
        0 AS depth
    FROM nodes n
    WHERE {src_where}
    
    UNION ALL
    
    -- Recursive case: follow edges
    SELECT
        n.id,
        t.path || n.id,
        t.amplification * COALESCE(e.amplification, 1.0),
        t.depth + 1
    FROM traverse t
    JOIN edges e ON t.id = e.from_id AND {edge_filter}
    JOIN nodes n ON e.to_id = n.id
    WHERE t.depth < {max_hops}
      AND n.id != ALL(t.path)  -- Prevent cycles
      AND {target_filter}
)
SELECT 
    t.path,
    t.amplification,
    t.depth,
    n.*
FROM traverse t
JOIN nodes n ON t.id = n.id
WHERE t.depth >= {min_hops}"""
        
        # ORDER BY
        if parsed['order_by']:
            order_parts = []
            for item in parsed['order_by']:
                order_parts.append(f"{item['expr']} {'DESC' if item['desc'] else 'ASC'}")
            sql += f"\nORDER BY {', '.join(order_parts)}"
        else:
            sql += "\nORDER BY t.amplification DESC, t.depth ASC"
        
        # LIMIT
        if parsed['limit']:
            sql += f"\nLIMIT {parsed['limit']}"
        
        return sql
    
    @classmethod
    def _transpile_create(cls, parsed: Dict[str, Any]) -> str:
        """Transpile CREATE query to INSERT."""
        # Simplified - just handle node creation
        return "-- CREATE not yet implemented"


# =============================================================================
# RECORD (Neo4j-compatible)
# =============================================================================

@dataclass
class Record:
    """
    Neo4j-compatible Record.
    
    Usage:
        for record in result:
            print(record['name'])
            print(record.get('age', 0))
    """
    _data: Dict[str, Any] = field(default_factory=dict)
    _keys: List[str] = field(default_factory=list)
    
    def __getitem__(self, key: Union[str, int]) -> Any:
        if isinstance(key, int):
            return self._data[self._keys[key]]
        return self._data[key]
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)
    
    def keys(self) -> List[str]:
        return self._keys
    
    def values(self) -> List[Any]:
        return [self._data[k] for k in self._keys]
    
    def items(self) -> List[Tuple[str, Any]]:
        return [(k, self._data[k]) for k in self._keys]
    
    def data(self) -> Dict[str, Any]:
        return dict(self._data)


# =============================================================================
# RESULT (Neo4j-compatible)
# =============================================================================

class Result:
    """
    Neo4j-compatible Result.
    
    Usage:
        result = session.run("MATCH (n) RETURN n")
        
        # Iterate
        for record in result:
            print(record['n'])
        
        # Get all
        records = result.data()
        
        # Single value
        count = result.single()['count']
    """
    
    def __init__(self, records: List[Record], keys: List[str]):
        self._records = records
        self._keys = keys
        self._index = 0
    
    def __iter__(self) -> Iterator[Record]:
        return iter(self._records)
    
    def __next__(self) -> Record:
        if self._index >= len(self._records):
            raise StopIteration
        record = self._records[self._index]
        self._index += 1
        return record
    
    def single(self) -> Optional[Record]:
        """Get single record (or None if empty)."""
        return self._records[0] if self._records else None
    
    def peek(self) -> Optional[Record]:
        """Peek at next record without consuming."""
        if self._index < len(self._records):
            return self._records[self._index]
        return None
    
    def data(self) -> List[Dict[str, Any]]:
        """Get all records as dicts."""
        return [r.data() for r in self._records]
    
    def keys(self) -> List[str]:
        """Get column keys."""
        return self._keys
    
    def values(self) -> List[List[Any]]:
        """Get all values."""
        return [r.values() for r in self._records]


# =============================================================================
# SESSION (Neo4j-compatible)
# =============================================================================

class Session:
    """
    Neo4j-compatible Session.
    
    Usage:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN n LIMIT 10")
            
            # Transactions
            with session.begin_transaction() as tx:
                tx.run("CREATE (n:Test {name: 'foo'})")
                tx.commit()
    """
    
    def __init__(self, db):
        self._db = db
        self._transaction = None
    
    def run(self, cypher: str, **params) -> Result:
        """
        Run Cypher query.
        
        Args:
            cypher: Cypher query string
            **params: Query parameters
        
        Returns:
            Result object
        """
        # Substitute parameters
        for key, value in params.items():
            if isinstance(value, str):
                cypher = cypher.replace(f'${key}', f"'{value}'")
            else:
                cypher = cypher.replace(f'${key}', str(value))
        
        # Transpile to SQL
        sql = CypherTranspiler.transpile(cypher)
        
        # Execute via database
        rows = self._db.execute_sql(sql)
        
        # Convert to Records
        keys = list(rows[0].keys()) if rows else []
        records = [Record(_data=dict(row), _keys=keys) for row in rows]
        
        return Result(records, keys)
    
    def begin_transaction(self) -> 'Transaction':
        """Begin a transaction."""
        self._transaction = Transaction(self._db)
        return self._transaction
    
    def close(self) -> None:
        """Close session."""
        if self._transaction:
            self._transaction.rollback()
            self._transaction = None
    
    def __enter__(self) -> 'Session':
        return self
    
    def __exit__(self, *args):
        self.close()


class Transaction:
    """Neo4j-compatible Transaction."""
    
    def __init__(self, db):
        self._db = db
        self._committed = False
        self._rolled_back = False
    
    def run(self, cypher: str, **params) -> Result:
        """Run query in transaction."""
        # Same as session.run for now (no real transactions in DuckDB in-memory)
        sql = CypherTranspiler.transpile(cypher)
        
        for key, value in params.items():
            if isinstance(value, str):
                sql = sql.replace(f'${key}', f"'{value}'")
            else:
                sql = sql.replace(f'${key}', str(value))
        
        rows = self._db.execute_sql(sql)
        keys = list(rows[0].keys()) if rows else []
        records = [Record(_data=dict(row), _keys=keys) for row in rows]
        return Result(records, keys)
    
    def commit(self) -> None:
        """Commit transaction."""
        self._committed = True
    
    def rollback(self) -> None:
        """Rollback transaction."""
        self._rolled_back = True
    
    def __enter__(self) -> 'Transaction':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        elif not self._committed:
            self.rollback()


# =============================================================================
# DRIVER (Neo4j-compatible)
# =============================================================================

class Driver:
    """
    Neo4j-compatible Driver.
    
    Usage:
        driver = GraphDatabase.driver("ladybug://./mydb")
        
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN n")
    """
    
    def __init__(self, uri: str, **config):
        self._uri = uri
        self._config = config
        self._db = self._connect()
    
    def _connect(self):
        """Connect to database."""
        # Import here to avoid circular dependency
        from ..core.unified_engine import LadybugEngine
        
        # Parse URI
        path = self._uri.replace('ladybug://', '').replace('bolt://', '')
        return LadybugEngine(path)
    
    def session(self, **config) -> Session:
        """Create a session."""
        return Session(self._db)
    
    def close(self) -> None:
        """Close driver."""
        pass
    
    def __enter__(self) -> 'Driver':
        return self
    
    def __exit__(self, *args):
        self.close()


# =============================================================================
# GRAPH DATABASE (Neo4j-compatible entry point)
# =============================================================================

class GraphDatabase:
    """
    Neo4j-compatible entry point.
    
    Usage:
        driver = GraphDatabase.driver("ladybug://./mydb")
    """
    
    @staticmethod
    def driver(uri: str, **config) -> Driver:
        """
        Create a driver.
        
        Args:
            uri: Connection URI (ladybug://path or bolt://host:port)
            **config: Driver configuration
        
        Returns:
            Driver instance
        """
        return Driver(uri, **config)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def cypher_to_sql(cypher: str) -> str:
    """Convert Cypher query to SQL."""
    return CypherTranspiler.transpile(cypher)


def parse_cypher(cypher: str) -> Dict[str, Any]:
    """Parse Cypher query into AST."""
    return CypherParser.parse(cypher)
