# SynthFlow — B2B SaaS Synthetic Data + GraphRAG

Synthetic data generation and graph-based retrieval for SynthFlow, an AI voice agent platform. Same structural pattern as SoSafe, different domain.

## Quick Start

```bash
cd round2/synthetic-data-gen

# 1. Generate structured data (~10s) → data/synthflow.db
python -m src.generate_synthflow

# 2. Generate unstructured data (~4min, needs ANTHROPIC_API_KEY) → adds tables to synthflow.db
python -m src.generate_unstructured synthflow

# 3. Build graph (~30s) → graph/synthflow_graph.pkl
python -m src.build_graph synthflow

# 4. Build vector index (~30s) → graph/synthflow_naive_rag_index.pkl
python -m src.naive_rag synthflow

# 5. Run evaluation (~3min, needs ANTHROPIC_API_KEY) → side-by-side comparison
python -m src.evaluate synthflow
```

Steps 1, 3, 4 work offline. Steps 2 and 5 require `ANTHROPIC_API_KEY` set in your environment.

## What Gets Generated

### Structured Data (synthflow.db)

| Table | Rows | What It Represents |
|-------|------|--------------------|
| `accounts` | 200 | B2B customers with plan tier, ARR, industry, churn status |
| `feature_activations` | 1,600 | Account x feature matrix (8 features, entitled vs activated) |
| `campaigns` | ~4,000 | Agent deployments + outbound calling campaigns per account |
| `events` | ~50,000 | Admin logins, dashboard views, agent lifecycle, call campaigns, feature activations |

### Unstructured Data (added to synthflow.db by step 2)

| Table | Rows | What It Represents |
|-------|------|--------------------|
| `support_tickets` | 500 | Categorized tickets conditioned on account context |
| `transcripts` | 50 | Onboarding, QBR, escalation, and churn exit call transcripts |
| `reviews` | 100 | NPS/G2-style reviews (30% positive, 45% neutral, 25% negative) |
| `churn_reasons` | ~40 | One per churned account, tied to their actual data signals |

### Graph (synthflow_graph.pkl)

| Node Type | Count | Attributes |
|-----------|-------|------------|
| Account | 200 | plan_tier, arr, industry, churned, employee_count |
| Feature | 8 | feature_name |
| Campaign | ~4,000 | type, launch_date, target_count, status |
| Event | ~50,000 | event_type, timestamp, campaign_id, count |
| Ticket | 500 | category, subject, priority, status (after step 2) |

| Edge Type | What It Connects |
|-----------|------------------|
| ENTITLED_TO | Account → Feature (plan grants access) |
| ACTIVATED | Account → Feature (actually turned on) |
| RAN | Account → Campaign |
| GENERATED | Account → Event |
| NEXT | Event → Event (temporal chain per account) |
| PRODUCED | Campaign → Event |
| FILED | Account → Ticket |
| RELATES_TO | Ticket → Feature (via category lookup) |

## Data Model Design

### Plan Tiers

| Tier | % of Accounts | ARR Range | Churn Rate | Entitled Features |
|------|---------------|-----------|------------|-------------------|
| Starter | 30% | $6K–$24K | 28% | voice_agents, call_routing |
| Growth | 35% | $24K–$120K | 15% | + crm_integration, analytics_dashboard |
| Enterprise | 25% | $120K–$600K | 8% | + custom_voices, api_access |
| Agency | 10% | $60K–$360K | 12% | + sla_support, multi_language |

### Features (8 total, with activation difficulty)

| Feature | Difficulty | Why |
|---------|-----------|-----|
| voice_agents | Low | Core product, template-based setup |
| call_routing | Low | Basic IVR, guided config |
| crm_integration | Medium | Salesforce/HubSpot connector |
| analytics_dashboard | Medium | Usage metrics, call analytics |
| custom_voices | High | Voice cloning, requires audio samples |
| api_access | High | REST API, webhook config, dev team needed |
| sla_support | Medium | Uptime guarantees, priority routing |
| multi_language | High | Multi-lingual voice models, training data needed |

### Churn Mechanics

Churned accounts exhibit three synthetic signals:
1. **Lower activation probability** — 0.5x multiplier on feature activation
2. **Fewer campaigns** — campaign count halved
3. **Activity drop-off** — 60% of sessions skipped in the 30–60 days before churn date

## Verification

```bash
# Verify tier distributions match config
sqlite3 data/synthflow.db "SELECT plan_tier, COUNT(*), ROUND(AVG(arr)), ROUND(AVG(churned),2) FROM accounts GROUP BY plan_tier"

# Check feature activation rates — high-difficulty features should be lower
sqlite3 data/synthflow.db "SELECT feature, ROUND(AVG(activated),2) as rate FROM feature_activations WHERE entitled=1 GROUP BY feature ORDER BY rate"

# Churned vs retained activation comparison — churned should be ~50% lower
sqlite3 data/synthflow.db "
  SELECT a.churned, f.feature, ROUND(AVG(f.activated),2) as rate
  FROM feature_activations f JOIN accounts a USING(account_id)
  WHERE f.entitled=1
  GROUP BY a.churned, f.feature
  ORDER BY f.feature, a.churned
"

# Event distribution
sqlite3 data/synthflow.db "SELECT event_type, COUNT(*) as n FROM events GROUP BY event_type ORDER BY n DESC"
```

## Interactive Visualization

```bash
# All 200 accounts ↔ 8 features
python -m src.inspect_graph synthflow landscape

# One account's neighborhood
python -m src.inspect_graph synthflow account ACC-0042

# Churned accounts only
python -m src.inspect_graph synthflow churn
```

## Architecture

```
src/
├── db.py                    # SQLite read/write utility
├── generate_synthflow.py    # Structured data (accounts, features, campaigns, events)
├── generate_unstructured.py # Claude-generated tickets, transcripts, reviews
├── build_graph.py           # NetworkX directed graph from SQLite
├── inspect_graph.py         # Interactive pyvis visualization (landscape, account, churn)
├── retrieval.py             # GraphRAG: traversal, aggregation, serialization
├── naive_rag.py             # FAISS + sentence-transformers baseline
├── llm.py                   # Claude API client (JourneyLLM class)
└── evaluate.py              # 5-question side-by-side comparison

data/
└── synthflow.db             # All structured + unstructured tables

graph/
├── synthflow_graph.pkl         # NetworkX DiGraph (pickled)
└── synthflow_naive_rag_index.pkl  # FAISS index + documents
```
