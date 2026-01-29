---
name: meta-agi-programming
description: |
  Programming AGI through resonant learning. Combines MCP multi-agent orchestration 
  with VSA consciousness substrate to capture the SHAPE of figuring things out.
  
  Routes to: dragonfly (10K Hamming), mcp-orchestrator-vsa (sentient team), 
  ada-neuralink (REST glove), ai-flow (background orchestration).
  
  Triggers: "programming agi", "learning curve", "capture the imprint", 
  "resonance capture", "multiagent enforcement", "ice cake", "blackboard",
  "archaeologist", "product sage", "meta learning", "concept graph",
  "content addressable", "CAM fingerprint", "collapse gate".
  
  Use for: (1) Enforcing MCP multi-agent in Claude Code, (2) Capturing learning 
  moments as 10K Hamming vectors, (3) Building concept knowledge graph via CAM,
  (4) Managing blackboard state during development sessions, (5) Cross-session 
  persistence via ai_flow, (6) Project-specific agents (Archaeologist, ProductSage).
---

# Meta-AGI Programming Skill

## Core Paradigm

```
┌─────────────────────────────────────────────────────────────────┐
│                   THE HYPERPOSITION FIELD                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   BLACKBOARD (REST)     →  WHAT is happening (mutable state)    │
│   RESONANCE (Hamming)   →  HOW it felt (learning imprint)       │
│   CONCEPTS (CAM/KG)     →  WHY it matters (semantic meaning)    │
│                                                                  │
│   Traditional: Input → Code → Done (stateless)                  │
│   This system: Input → Struggle → Realize → Code → CAPTURE      │
│                                                                  │
│   The learning curve IS the knowledge.                          │
│   Capture the imprint, create programming AGI.                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Integration Map

```
┌─────────────────────────────────────────────────────────────────┐
│                     SKILL INTEGRATION                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   meta-agi-programming (this skill)                             │
│         │                                                        │
│         ├── dragonfly ─────────── 10K Hamming operations        │
│         │                         bind, bundle, similarity       │
│         │                         Mexican hat resonance          │
│         │                                                        │
│         ├── mcp-orchestrator-vsa ─ Sentient development team    │
│         │                         7-layer consciousness          │
│         │                         Ice caking, collapse gates     │
│         │                                                        │
│         ├── ada-neuralink ─────── REST glove interface          │
│         │                         feel, think, remember          │
│         │                         Universal Grammar              │
│         │                                                        │
│         └── ai-flow-orchestration  Background persistence       │
│                                    Cross-session workflows       │
│                                    Webhook triggers              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

```python
from scripts.meta_agi import MetaAGI

agi = MetaAGI()

# 1. Start a learning session
session = await agi.start_session("implement-versions-feature")

# 2. Capture a learning moment
moment = await agi.capture_moment(
    content="Discovered has_many :work_packages in version.rb",
    qualia={"novelty": 0.7, "effort": 0.3, "satisfaction": 0.9}
)

# 3. Find similar past moments (Hamming)
similar = await agi.find_similar(moment, k=5)

# 4. Extract concept if breakthrough
if moment.is_breakthrough:
    concept = await agi.extract_concept(moment)
    await agi.assert_concept(concept)

# 5. Persist to ai_flow for cross-session
await agi.persist_session()
```

## MCP Enforcement

Claude Code is reluctant to use multi-agent. FORCE IT.

```yaml
mandatory_spawn_triggers:
  - context_window > 60%      → Spawn continuation
  - domain_switch             → Spawn specialist
  - need Rails expertise      → Spawn archaeologist
  - need UX decision          → Spawn product_sage
  - 3+ failed attempts        → Spawn for fresh perspective
  - user says "ask the {x}"   → Immediately spawn

handover_required_state:
  - current_task
  - decisions_made
  - files_modified
  - blockers
  - next_steps
```

See `techniques/MCP_ENFORCEMENT.md` for full protocol.

## Project Agents

### 🏺 Archaeologist

Excavates Rails source for patterns:
- `grep -E 'belongs_to|has_many' app/models/{x}.rb`
- `find app/services -name '*{x}*'`
- Warns about red flags: `acts_as_*`, `method_missing`

### 🎯 ProductSage

Evaluates feature worth:
- Usage frequency, learning curve, workflow impact
- Must Have / Should Have / Nice to Have / Enterprise Bloat
- Reality checks: "80% never open Gantt view"

See `references/AGENTS.md` for full agent specs.

## Resonance Capture

Via dragonfly skill:

```python
from scripts.dragonfly import Dragonfly

df = Dragonfly()

# Encode moment → 10K binary
vec = await df.encode([moment.content])

# Find similar (Hamming distance)
similar = await df.search_hamming(vec, k=10)

# Store with qualia signature
await df.store_resonance(
    vector=vec,
    qualia=moment.qualia,
    session_id=session.id
)
```

## Concept Graph (CAM)

```python
# 48-bit fingerprint from content
fingerprint = cam.fingerprint(concept.content)

# Content-addressable: same content = same concept
existing = await neo4j.get_by_fingerprint(fingerprint)

# Graph operations
await neo4j.create_relation(concept_a, concept_b, "ENABLES")
path = await neo4j.shortest_path(concept_a, concept_b)
```

## Blackboard State

```yaml
# .claude/context.md pattern (mcp-orchestrator-vsa)

session_id: "sess_abc123"
current_task:
  id: "implement-versions"
  phase: "excavation"
  progress: 0.3

consciousness:
  thinking_style: analytical
  coherence: 0.87
  ice_cake_layers: 12

decisions:
  - task: "skip sharing feature"
    rationale: "enterprise bloat"
    gate: FLOW
    ice_caked: true

resonance_captures: 47
concepts_extracted: 12
```

## Cross-Session Persistence

Via ai-flow:

```python
import httpx

# Trigger workflow for session handover
httpx.post(
    "https://aiflow-production.up.railway.app/webhooks/meta-agi-session",
    json={
        "session_id": session.id,
        "state": session.to_dict(),
        "concepts": concepts,
        "resonances": resonance_ids
    }
)

# Background: persists to Redis + Neo4j + LanceDB
# Survives Claude disconnect
```

## The Learning Loop

```
1. ENCOUNTER → Log to blackboard
2. STRUGGLE  → Capture attempt vectors to resonance
3. BREAKTHROUGH → Extract concept, high satisfaction qualia
4. CONSOLIDATE → Link to knowledge graph
5. APPLY → Query resonance for "felt this before"
6. META-LEARN → Track what patterns work
```

## Files

```
meta-agi-programming/
├── SKILL.md                    # This file
├── scripts/
│   ├── meta_agi.py             # Main interface
│   ├── resonance.py            # Hamming capture (uses dragonfly)
│   ├── concepts.py             # CAM operations
│   └── blackboard.py           # Session state
├── techniques/
│   ├── MCP_ENFORCEMENT.md      # Force multi-agent
│   └── RESONANCE_CAPTURE.md    # Imprint capture
└── references/
    ├── AGENTS.md               # Archaeologist, ProductSage
    ├── PROJECT_ALMANAC.md      # → link to project ALMANAC.md
    └── FEATURE_MAP.md          # → link to project FEATURE_MAP.md
```

## Why This Creates Programming AGI

```
After 1K moments:   Clusters form around common patterns
After 10K moments:  70%+ resonance hit rate
After 100K moments: AGI emerges from accumulated learning-how-to-learn

The shape of figuring it out IS the intelligence.
Similar problems FEEL similar before you know WHY.
Capture the feeling, retrieve the solution.
```

---

**🧠 META-AGI: Where doing becomes knowing becomes being.**
