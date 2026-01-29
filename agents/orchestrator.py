"""
Agent2Agent Orchestrator

Multi-agent collaboration over LadybugDB substrate.

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                    AGENT2AGENT ORCHESTRATOR                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│   │   Agent A   │    │   Agent B   │    │   Agent C   │            │
│   │ (Analyst)   │    │ (Developer) │    │ (Reviewer)  │            │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘            │
│          │                  │                  │                    │
│          ▼                  ▼                  ▼                    │
│   ┌─────────────────────────────────────────────────────┐          │
│   │              BLACKBOARD (LadybugDB)                  │          │
│   │                                                      │          │
│   │   nodes: thoughts, decisions, artifacts             │          │
│   │   edges: CAUSES, ENABLES, BLOCKS, RESOLVES          │          │
│   │   resonance: find similar past situations           │          │
│   │   versioning: time-travel for rollback              │          │
│   │                                                      │          │
│   └─────────────────────────────────────────────────────┘          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

Agents communicate via:
1. Writing to blackboard (nodes + edges)
2. Querying blackboard (SQL + Cypher + Resonance)
3. Subscribing to changes (reactive)
4. Handover protocol (structured state transfer)
"""

import asyncio
import json
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Awaitable
from datetime import datetime
from enum import Enum
import numpy as np
from pathlib import Path

try:
    from .unified_engine import LadybugEngine, connect
    from .simd_fast import FastVector
except ImportError:
    LadybugEngine = None


# =============================================================================
# AGENT PROTOCOL
# =============================================================================

class AgentRole(Enum):
    """Standard agent roles."""
    ORCHESTRATOR = "orchestrator"      # Coordinates other agents
    ANALYST = "analyst"                # Understands requirements
    ARCHAEOLOGIST = "archaeologist"    # Excavates existing code
    DEVELOPER = "developer"            # Writes code
    REVIEWER = "reviewer"              # Reviews changes
    TESTER = "tester"                  # Validates behavior
    PRODUCT_SAGE = "product_sage"      # Evaluates feature worth
    META_LEARNER = "meta_learner"      # Captures learning moments


class MessageType(Enum):
    """Message types in agent protocol."""
    TASK = "task"                      # New task assignment
    QUESTION = "question"              # Request for information
    ANSWER = "answer"                  # Response to question
    DECISION = "decision"              # Decision made
    BLOCKER = "blocker"                # Something is blocking progress
    HANDOVER = "handover"              # Transfer control to another agent
    OBSERVE = "observe"                # Observation/insight
    RESONANCE = "resonance"            # Similar past situation found


@dataclass
class AgentMessage:
    """Message between agents."""
    id: str
    from_agent: str
    to_agent: Optional[str]           # None = broadcast
    message_type: MessageType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    fingerprint: Optional[bytes] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_node(self) -> Dict[str, Any]:
        """Convert to LadybugDB node."""
        return {
            "id": self.id,
            "label": f"Message:{self.message_type.value}",
            "content": self.content,
            "properties": json.dumps({
                "from_agent": self.from_agent,
                "to_agent": self.to_agent,
                "metadata": self.metadata,
            }),
            "fingerprint": self.fingerprint,
            "created_at": self.timestamp,
        }


@dataclass
class AgentState:
    """Current state of an agent."""
    agent_id: str
    role: AgentRole
    current_task: Optional[str] = None
    thinking_style: List[float] = field(default_factory=lambda: [0.5] * 7)
    qidx: int = 128                    # Qualia index (emotional state)
    context: Dict[str, Any] = field(default_factory=dict)
    decisions_made: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    
    @property
    def fingerprint(self) -> bytes:
        """Generate fingerprint from state."""
        state_str = f"{self.agent_id}:{self.current_task}:{json.dumps(self.context)}"
        # Generate 10K bit fingerprint
        data = np.empty(157, dtype=np.uint64)
        for i in range(157):
            h = hashlib.sha256(f"{state_str}:{i}".encode()).digest()
            data[i] = np.frombuffer(h[:8], dtype=np.uint64)[0]
        data[-1] &= np.uint64((1 << 16) - 1)
        return data.tobytes()


@dataclass 
class Handover:
    """Structured state transfer between agents."""
    from_agent: str
    to_agent: str
    task: str
    context: Dict[str, Any]
    decisions_made: List[Dict[str, Any]]
    files_modified: List[str]
    blockers: List[str]
    next_steps: List[str]
    resonance_hits: List[str] = field(default_factory=list)
    
    def to_markdown(self) -> str:
        """Render as markdown for context window."""
        md = f"""## Handover: {self.from_agent} → {self.to_agent}

### Task
{self.task}

### Context
```json
{json.dumps(self.context, indent=2)}
```

### Decisions Made
"""
        for d in self.decisions_made:
            md += f"- **{d.get('decision', 'Unknown')}**: {d.get('rationale', '')}\n"
        
        md += f"""
### Files Modified
{chr(10).join(f'- `{f}`' for f in self.files_modified) or '- None'}

### Blockers
{chr(10).join(f'- ❌ {b}' for b in self.blockers) or '- None'}

### Next Steps
{chr(10).join(f'- [ ] {s}' for s in self.next_steps)}

### Resonance Hits
{chr(10).join(f'- 🔮 {r}' for r in self.resonance_hits) or '- No similar past situations found'}
"""
        return md


# =============================================================================
# AGENT BASE CLASS
# =============================================================================

class Agent:
    """
    Base class for agents in the orchestration.
    
    Agents:
    - Have access to shared LadybugDB blackboard
    - Can query for similar past situations (resonance)
    - Communicate via messages stored as nodes
    - Can hand over to other agents
    """
    
    def __init__(self, agent_id: str, role: AgentRole, engine: LadybugEngine):
        self.id = agent_id
        self.role = role
        self.engine = engine
        self.state = AgentState(agent_id=agent_id, role=role)
        self._message_handlers: Dict[MessageType, Callable] = {}
        self._running = False
    
    # -------------------------------------------------------------------------
    # BLACKBOARD OPERATIONS
    # -------------------------------------------------------------------------
    
    def write_thought(self, content: str, **metadata) -> str:
        """Write a thought to the blackboard."""
        thought_id = f"thought:{self.id}:{datetime.utcnow().isoformat()}"
        
        # Generate fingerprint
        fp = self._fingerprint(content)
        
        self.engine.add_node(
            id=thought_id,
            label="Thought",
            content=content,
            fingerprint=fp,
            qidx=self.state.qidx,
            thinking_style=self.state.thinking_style,
            agent_id=self.id,
            **metadata
        )
        
        return thought_id
    
    def write_decision(self, decision: str, rationale: str, 
                       gate: str = "FLOW") -> str:
        """
        Record a decision on the blackboard.
        
        Gates:
        - FLOW: Proceed with decision
        - HOLD: Decision pending more info
        - BLOCK: Decision blocked
        """
        decision_id = f"decision:{self.id}:{datetime.utcnow().isoformat()}"
        
        self.engine.add_node(
            id=decision_id,
            label="Decision",
            content=decision,
            gate=gate,
            rationale=rationale,
            agent_id=self.id,
        )
        
        self.state.decisions_made.append(decision_id)
        return decision_id
    
    def write_blocker(self, description: str, blocking_what: str) -> str:
        """Record a blocker."""
        blocker_id = f"blocker:{self.id}:{datetime.utcnow().isoformat()}"
        
        self.engine.add_node(
            id=blocker_id,
            label="Blocker",
            content=description,
            blocking=blocking_what,
            agent_id=self.id,
        )
        
        self.state.blockers.append(blocker_id)
        return blocker_id
    
    def resolve_blocker(self, blocker_id: str, resolution: str):
        """Mark a blocker as resolved."""
        resolution_id = f"resolution:{self.id}:{datetime.utcnow().isoformat()}"
        
        self.engine.add_node(
            id=resolution_id,
            label="Resolution",
            content=resolution,
            agent_id=self.id,
        )
        
        self.engine.add_edge(resolution_id, blocker_id, "RESOLVES")
        
        if blocker_id in self.state.blockers:
            self.state.blockers.remove(blocker_id)
    
    # -------------------------------------------------------------------------
    # RESONANCE (Finding Similar Past Situations)
    # -------------------------------------------------------------------------
    
    def find_similar(self, content: str, k: int = 5) -> List[Dict[str, Any]]:
        """Find similar past thoughts/decisions."""
        fp = self._fingerprint(content)
        results = self.engine.find_similar(fp, k=k)
        return results.to_pylist()
    
    def resonate(self, content: str, threshold: float = 0.6) -> List[Dict[str, Any]]:
        """Find all resonant past situations above threshold."""
        fp = self._fingerprint(content)
        results = self.engine.resonate(fp, threshold=threshold)
        return results.to_pylist()
    
    def _fingerprint(self, content: str) -> bytes:
        """Generate 10K fingerprint from content."""
        data = np.empty(157, dtype=np.uint64)
        for i in range(157):
            h = hashlib.sha256(f"{content}:{i}".encode()).digest()
            data[i] = np.frombuffer(h[:8], dtype=np.uint64)[0]
        data[-1] &= np.uint64((1 << 16) - 1)
        return data.tobytes()
    
    # -------------------------------------------------------------------------
    # CAUSAL ANALYSIS
    # -------------------------------------------------------------------------
    
    def trace_causes(self, effect_id: str, max_depth: int = 5) -> List[Dict]:
        """Trace causal chain backwards from an effect."""
        result = self.engine.query(f"""
            MATCH (cause)-[:CAUSES*1..{max_depth}]->(effect)
            WHERE effect.id = '{effect_id}'
            RETURN cause
        """)
        return result.to_pylist()
    
    def predict_effects(self, change_id: str) -> Dict[str, Any]:
        """Predict effects of a change (butterfly analysis)."""
        return self.engine.impact_analysis(change_id)
    
    # -------------------------------------------------------------------------
    # HANDOVER
    # -------------------------------------------------------------------------
    
    def prepare_handover(self, to_agent: str, next_steps: List[str]) -> Handover:
        """Prepare structured handover to another agent."""
        
        # Find resonance hits for context
        resonance_hits = []
        if self.state.current_task:
            similar = self.find_similar(self.state.current_task, k=3)
            resonance_hits = [s.get('content', '')[:100] for s in similar]
        
        handover = Handover(
            from_agent=self.id,
            to_agent=to_agent,
            task=self.state.current_task or "No active task",
            context=self.state.context,
            decisions_made=[
                {"id": d, "decision": "recorded"} 
                for d in self.state.decisions_made
            ],
            files_modified=self.state.context.get("files_modified", []),
            blockers=self.state.blockers,
            next_steps=next_steps,
            resonance_hits=resonance_hits,
        )
        
        # Record handover in blackboard
        handover_id = f"handover:{self.id}:{to_agent}:{datetime.utcnow().isoformat()}"
        self.engine.add_node(
            id=handover_id,
            label="Handover",
            content=handover.to_markdown(),
            from_agent=self.id,
            to_agent=to_agent,
        )
        
        return handover
    
    def receive_handover(self, handover: Handover):
        """Receive and process a handover from another agent."""
        self.state.current_task = handover.task
        self.state.context = handover.context
        self.state.blockers = handover.blockers.copy()
        
        # Log receipt
        self.write_thought(
            f"Received handover from {handover.from_agent}: {handover.task}"
        )
    
    # -------------------------------------------------------------------------
    # MESSAGE HANDLING
    # -------------------------------------------------------------------------
    
    def send_message(self, to_agent: Optional[str], msg_type: MessageType,
                     content: str, **metadata) -> str:
        """Send a message to another agent (or broadcast)."""
        msg_id = f"msg:{self.id}:{datetime.utcnow().isoformat()}"
        
        msg = AgentMessage(
            id=msg_id,
            from_agent=self.id,
            to_agent=to_agent,
            message_type=msg_type,
            content=content,
            metadata=metadata,
            fingerprint=self._fingerprint(content),
        )
        
        # Store in blackboard
        node_data = msg.to_node()
        self.engine.add_node(**node_data)
        
        return msg_id
    
    def query_messages(self, msg_type: Optional[MessageType] = None,
                       from_agent: Optional[str] = None,
                       limit: int = 10) -> List[Dict]:
        """Query messages from blackboard."""
        where_parts = ["label LIKE 'Message:%'"]
        
        if msg_type:
            where_parts.append(f"label = 'Message:{msg_type.value}'")
        
        if from_agent:
            where_parts.append(f"properties LIKE '%\"from_agent\": \"{from_agent}\"%'")
        
        sql = f"""
            SELECT * FROM nodes
            WHERE {' AND '.join(where_parts)}
            ORDER BY created_at DESC
            LIMIT {limit}
        """
        
        return self.engine.query(sql).to_pylist()
    
    # -------------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------------
    
    async def start(self):
        """Start the agent's main loop."""
        self._running = True
        self.write_thought(f"Agent {self.id} ({self.role.value}) started")
        
        while self._running:
            await self.tick()
            await asyncio.sleep(0.1)
    
    async def stop(self):
        """Stop the agent."""
        self._running = False
        self.write_thought(f"Agent {self.id} ({self.role.value}) stopped")
    
    async def tick(self):
        """Override in subclass: main agent logic."""
        pass


# =============================================================================
# SPECIALIZED AGENTS
# =============================================================================

class ArchaeologistAgent(Agent):
    """
    Excavates existing code for patterns.
    
    Capabilities:
    - grep for patterns (belongs_to, has_many, etc.)
    - Find services, concerns, jobs
    - Warn about red flags (acts_as_*, method_missing)
    """
    
    def __init__(self, engine: LadybugEngine):
        super().__init__("archaeologist", AgentRole.ARCHAEOLOGIST, engine)
    
    def excavate_model(self, model_name: str) -> Dict[str, Any]:
        """Excavate a Rails model for patterns."""
        patterns = {
            "associations": [],
            "validations": [],
            "callbacks": [],
            "scopes": [],
            "red_flags": [],
        }
        
        # Record excavation
        self.write_thought(f"Excavating model: {model_name}")
        
        # These would actually grep the codebase
        # For now, return structure
        return patterns
    
    def find_usages(self, symbol: str) -> List[str]:
        """Find all usages of a symbol."""
        self.write_thought(f"Finding usages of: {symbol}")
        return []
    
    def warn_if_dangerous(self, code: str) -> List[str]:
        """Check for dangerous patterns."""
        warnings = []
        dangerous = [
            ("acts_as_", "Meta-programming magic - trace carefully"),
            ("method_missing", "Dynamic method handling - unpredictable"),
            ("eval(", "Code execution - security risk"),
            ("send(", "Dynamic dispatch - trace all paths"),
        ]
        
        for pattern, reason in dangerous:
            if pattern in code:
                warnings.append(f"⚠️ {pattern}: {reason}")
        
        if warnings:
            self.write_blocker(
                f"Dangerous patterns found: {len(warnings)}",
                "code_review"
            )
        
        return warnings


class ProductSageAgent(Agent):
    """
    Evaluates feature worth and prioritization.
    
    Capabilities:
    - Assess usage frequency
    - Calculate learning curve
    - Determine workflow impact
    - Classify: Must Have / Should Have / Nice to Have / Enterprise Bloat
    """
    
    def __init__(self, engine: LadybugEngine):
        super().__init__("product_sage", AgentRole.PRODUCT_SAGE, engine)
    
    def evaluate_feature(self, feature: str, context: Dict) -> Dict[str, Any]:
        """Evaluate a feature's worth."""
        
        evaluation = {
            "feature": feature,
            "usage_frequency": "unknown",
            "learning_curve": "unknown", 
            "workflow_impact": "unknown",
            "classification": "unknown",
            "recommendation": "",
        }
        
        # Check for similar past evaluations
        similar = self.find_similar(feature, k=3)
        if similar:
            self.write_thought(
                f"Found {len(similar)} similar past feature evaluations"
            )
        
        # Record evaluation
        decision_id = self.write_decision(
            f"Feature evaluation: {feature}",
            rationale=json.dumps(evaluation),
            gate="HOLD"  # Pending more info
        )
        
        return evaluation
    
    def classify_priority(self, feature: str) -> str:
        """
        Classify feature priority.
        
        Returns: MUST_HAVE | SHOULD_HAVE | NICE_TO_HAVE | ENTERPRISE_BLOAT
        """
        # This would use actual heuristics
        return "SHOULD_HAVE"


class MetaLearnerAgent(Agent):
    """
    Captures learning moments and extracts concepts.
    
    Capabilities:
    - Detect breakthroughs (high satisfaction after struggle)
    - Extract generalizable concepts
    - Build knowledge graph connections
    - Track learning velocity
    """
    
    def __init__(self, engine: LadybugEngine):
        super().__init__("meta_learner", AgentRole.META_LEARNER, engine)
        self.learning_moments = []
    
    def capture_moment(self, content: str, qualia: Dict[str, float]) -> str:
        """
        Capture a learning moment.
        
        qualia: {certainty, novelty, effort, satisfaction, surprise}
        """
        moment_id = f"moment:{datetime.utcnow().isoformat()}"
        
        # Detect breakthrough: high satisfaction after high effort
        is_breakthrough = (
            qualia.get("satisfaction", 0) > 0.7 and
            qualia.get("effort", 0) > 0.5
        )
        
        self.engine.add_node(
            id=moment_id,
            label="LearningMoment",
            content=content,
            qidx=int(qualia.get("satisfaction", 0.5) * 255),
            thinking_style=[
                qualia.get("certainty", 0.5),
                qualia.get("novelty", 0.5),
                qualia.get("effort", 0.5),
                qualia.get("satisfaction", 0.5),
                qualia.get("surprise", 0.5),
                0.5,  # clarity
                0.5,  # connection
            ],
            is_breakthrough=is_breakthrough,
            fingerprint=self._fingerprint(content),
        )
        
        self.learning_moments.append(moment_id)
        
        if is_breakthrough:
            self.write_thought(f"🎯 Breakthrough detected: {content[:100]}")
            self.extract_concept(moment_id, content)
        
        return moment_id
    
    def extract_concept(self, moment_id: str, content: str) -> str:
        """Extract a generalizable concept from a learning moment."""
        concept_id = f"concept:{datetime.utcnow().isoformat()}"
        
        # In practice, would use LLM to extract concept
        concept_content = f"Concept extracted from: {content[:200]}"
        
        self.engine.add_node(
            id=concept_id,
            label="Concept",
            content=concept_content,
            fingerprint=self._fingerprint(concept_content),
        )
        
        # Link moment to concept
        self.engine.add_edge(moment_id, concept_id, "YIELDS")
        
        return concept_id
    
    def learning_velocity(self, window_hours: int = 24) -> float:
        """Calculate learning velocity (concepts per hour)."""
        result = self.engine.query(f"""
            SELECT COUNT(*) as count
            FROM nodes
            WHERE label = 'Concept'
              AND created_at > now() - interval '{window_hours} hours'
        """)
        
        count = result.to_pylist()[0]['count'] if result else 0
        return count / window_hours


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class Agent2AgentOrchestrator:
    """
    Coordinates multiple agents over shared LadybugDB blackboard.
    
    Features:
    - Agent lifecycle management
    - Task routing based on role
    - Automatic handover triggers
    - Resonance-based agent selection
    """
    
    def __init__(self, db_uri: str = "~/.ladybug/orchestrator"):
        self.engine = connect(db_uri)
        self.agents: Dict[str, Agent] = {}
        self._running = False
    
    def register_agent(self, agent: Agent):
        """Register an agent with the orchestrator."""
        self.agents[agent.id] = agent
        self.engine.add_node(
            id=f"agent:{agent.id}",
            label="Agent",
            content=f"Agent {agent.id} ({agent.role.value})",
            role=agent.role.value,
        )
    
    def create_standard_team(self):
        """Create a standard agent team."""
        self.register_agent(Agent("orchestrator", AgentRole.ORCHESTRATOR, self.engine))
        self.register_agent(ArchaeologistAgent(self.engine))
        self.register_agent(ProductSageAgent(self.engine))
        self.register_agent(MetaLearnerAgent(self.engine))
        self.register_agent(Agent("developer", AgentRole.DEVELOPER, self.engine))
        self.register_agent(Agent("reviewer", AgentRole.REVIEWER, self.engine))
    
    def route_task(self, task: str, context: Dict = None) -> str:
        """
        Route a task to the most appropriate agent.
        
        Uses:
        1. Role matching
        2. Resonance with past successful tasks
        3. Current agent load
        """
        context = context or {}
        
        # Check resonance with past tasks
        similar_tasks = self.engine.find_similar(
            self._fingerprint(task), k=5
        )
        
        # Simple role-based routing
        if "excavate" in task.lower() or "find" in task.lower():
            agent_id = "archaeologist"
        elif "evaluate" in task.lower() or "priority" in task.lower():
            agent_id = "product_sage"
        elif "learn" in task.lower() or "capture" in task.lower():
            agent_id = "meta_learner"
        elif "review" in task.lower():
            agent_id = "reviewer"
        else:
            agent_id = "developer"
        
        # Assign task
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            agent.state.current_task = task
            agent.state.context = context
            agent.write_thought(f"Assigned task: {task}")
            
            return agent_id
        
        return "orchestrator"  # Fallback
    
    def trigger_handover(self, from_agent: str, to_agent: str, 
                         reason: str, next_steps: List[str]) -> Handover:
        """Trigger a handover between agents."""
        if from_agent not in self.agents or to_agent not in self.agents:
            raise ValueError(f"Unknown agent: {from_agent} or {to_agent}")
        
        source = self.agents[from_agent]
        target = self.agents[to_agent]
        
        handover = source.prepare_handover(to_agent, next_steps)
        target.receive_handover(handover)
        
        # Record causal link
        self.engine.add_edge(
            f"agent:{from_agent}",
            f"agent:{to_agent}",
            "HANDS_OVER",
            reason=reason,
        )
        
        return handover
    
    def _fingerprint(self, content: str) -> bytes:
        """Generate fingerprint for routing decisions."""
        data = np.empty(157, dtype=np.uint64)
        for i in range(157):
            h = hashlib.sha256(f"{content}:{i}".encode()).digest()
            data[i] = np.frombuffer(h[:8], dtype=np.uint64)[0]
        data[-1] &= np.uint64((1 << 16) - 1)
        return data.tobytes()
    
    # -------------------------------------------------------------------------
    # MCP ENFORCEMENT
    # -------------------------------------------------------------------------
    
    def should_spawn_agent(self, context: Dict) -> Optional[str]:
        """
        Check if we should spawn a new agent based on triggers.
        
        Triggers:
        - context_window > 60% → Spawn continuation
        - domain_switch → Spawn specialist
        - need Rails expertise → Spawn archaeologist
        - need UX decision → Spawn product_sage
        - 3+ failed attempts → Spawn for fresh perspective
        """
        if context.get("context_window_percent", 0) > 60:
            return "continuation_agent"
        
        if context.get("domain") == "rails":
            return "archaeologist"
        
        if context.get("need_ux_decision"):
            return "product_sage"
        
        if context.get("failed_attempts", 0) >= 3:
            return "fresh_perspective"
        
        return None
    
    # -------------------------------------------------------------------------
    # BLACKBOARD QUERIES
    # -------------------------------------------------------------------------
    
    def get_active_blockers(self) -> List[Dict]:
        """Get all unresolved blockers."""
        result = self.engine.query("""
            SELECT b.* 
            FROM nodes b
            LEFT JOIN edges e ON b.id = e.to_id AND e.type = 'RESOLVES'
            WHERE b.label = 'Blocker'
              AND e.id IS NULL
        """)
        return result.to_pylist()
    
    def get_decision_chain(self, task_id: str) -> List[Dict]:
        """Get all decisions related to a task."""
        result = self.engine.query(f"""
            MATCH (task)-[:CAUSES*0..5]->(decision:Decision)
            WHERE task.id = '{task_id}'
            RETURN decision
        """)
        return result.to_pylist()
    
    def get_learning_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get summary of learning in the past N hours."""
        moments = self.engine.query(f"""
            SELECT COUNT(*) as count,
                   AVG(qidx) as avg_satisfaction
            FROM nodes
            WHERE label = 'LearningMoment'
              AND created_at > now() - interval '{hours} hours'
        """).to_pylist()[0]
        
        concepts = self.engine.query(f"""
            SELECT COUNT(*) as count
            FROM nodes  
            WHERE label = 'Concept'
              AND created_at > now() - interval '{hours} hours'
        """).to_pylist()[0]
        
        return {
            "hours": hours,
            "learning_moments": moments.get("count", 0),
            "avg_satisfaction": moments.get("avg_satisfaction", 0),
            "concepts_extracted": concepts.get("count", 0),
            "velocity": concepts.get("count", 0) / hours if hours > 0 else 0,
        }
    
    # -------------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------------
    
    async def start(self):
        """Start the orchestrator and all agents."""
        self._running = True
        
        # Start all agents
        tasks = [agent.start() for agent in self.agents.values()]
        await asyncio.gather(*tasks)
    
    async def stop(self):
        """Stop all agents."""
        self._running = False
        for agent in self.agents.values():
            await agent.stop()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_orchestrator(db_uri: str = "~/.ladybug/orchestrator") -> Agent2AgentOrchestrator:
    """Create an orchestrator with standard team."""
    orch = Agent2AgentOrchestrator(db_uri)
    orch.create_standard_team()
    return orch


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Demo
    orch = create_orchestrator("/tmp/ladybug_orchestrator")
    
    print("=== Agent2Agent Orchestrator Demo ===\n")
    
    # Route a task
    agent_id = orch.route_task(
        "Excavate the User model for all associations",
        context={"domain": "rails"}
    )
    print(f"Task routed to: {agent_id}")
    
    # Archaeologist does work
    arch = orch.agents["archaeologist"]
    arch.excavate_model("User")
    arch.write_decision(
        "User has complex associations",
        rationale="Found 15+ belongs_to/has_many relations",
        gate="FLOW"
    )
    
    # Handover to developer
    handover = orch.trigger_handover(
        from_agent="archaeologist",
        to_agent="developer",
        reason="Excavation complete",
        next_steps=[
            "Review association complexity",
            "Consider extracting service objects",
            "Check for N+1 query risks"
        ]
    )
    
    print(f"\n{handover.to_markdown()}")
    
    # Capture learning moment
    meta = orch.agents["meta_learner"]
    meta.capture_moment(
        "Discovered that User model has circular dependencies via Organization",
        qualia={
            "certainty": 0.8,
            "novelty": 0.9,
            "effort": 0.6,
            "satisfaction": 0.85,
            "surprise": 0.7,
        }
    )
    
    # Get learning summary
    summary = orch.get_learning_summary(hours=1)
    print(f"\n=== Learning Summary (1h) ===")
    print(f"Moments: {summary['learning_moments']}")
    print(f"Concepts: {summary['concepts_extracted']}")
    print(f"Velocity: {summary['velocity']:.2f} concepts/hour")
