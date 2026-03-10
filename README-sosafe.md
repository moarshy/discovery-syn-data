# SoSafe — B2B SaaS Synthetic Data + GraphRAG

Synthetic data generation and graph-based retrieval for SoSafe, a cybersecurity awareness platform. Built for Tiago's feature activation analysis use case.

## Quick Start

```bash
cd round2/synthetic-data-gen

# 1. Generate structured data (~10s) → data/sosafe.db
python -m src.generate_sosafe

# 2. Generate unstructured data (~4min, needs ANTHROPIC_API_KEY) → adds tables to sosafe.db
python -m src.generate_unstructured sosafe

# 3. Build graph (~30s) → graph/sosafe_graph.pkl
python -m src.build_graph sosafe

# 4. Build vector index (~30s) → graph/sosafe_naive_rag_index.pkl
python -m src.naive_rag sosafe

# 5. Run evaluation (~3min, needs ANTHROPIC_API_KEY) → side-by-side comparison
python -m src.evaluate sosafe
```

Steps 1, 3, 4 work offline. Steps 2 and 5 require `ANTHROPIC_API_KEY` set in your environment.

## What Gets Generated

### Structured Data (sosafe.db)

| Table | Rows | What It Represents |
|-------|------|--------------------|
| `accounts` | 200 | B2B customers with plan tier, ARR, industry, churn status |
| `feature_activations` | 1,600 | Account x feature matrix (8 features, entitled vs activated) |
| `campaigns` | ~4,000 | Phishing simulations + e-learning campaigns per account |
| `events` | ~61,000 | Admin logins, dashboard views, campaign lifecycle, feature activations |

### Unstructured Data (added to sosafe.db by step 2)

| Table | Rows | What It Represents |
|-------|------|--------------------|
| `support_tickets` | 500 | Categorized tickets conditioned on account context |
| `transcripts` | 50 | Onboarding, QBR, escalation, and churn exit call transcripts |
| `reviews` | 100 | NPS/G2-style reviews (30% positive, 45% neutral, 25% negative) |
| `churn_reasons` | ~30 | One per churned account, tied to their actual data signals |

### Graph (sosafe_graph.pkl)

| Node Type | Count | Attributes |
|-----------|-------|------------|
| Account | 200 | plan_tier, arr, industry, churned, employee_count |
| Feature | 8 | feature_name, activation_difficulty |
| Campaign | ~4,000 | type, launch_date, target_count, status |
| Event | ~61,000 | event_type, timestamp, campaign_id, count |
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

### Plan Tiers (maps to SoSafe's actual pricing)

| Tier | % of Accounts | ARR Range | Churn Rate | Entitled Features |
|------|---------------|-----------|------------|-------------------|
| Essential | 35% | $5K–$20K | 25% | elearning, basic_phishing |
| Professional | 35% | $20K–$80K | 15% | + advanced_phishing, report_button |
| Premium | 20% | $80K–$250K | 8% | + sofie, human_risk_os |
| Ultimate | 10% | $250K–$800K | 5% | + sso, scim |

### Features (8 total, with activation difficulty)

| Feature | Difficulty | Why |
|---------|-----------|-----|
| elearning | Low | Self-serve, no IT dependency |
| basic_phishing | Low | Core product, guided setup |
| advanced_phishing | Medium | Requires campaign design skill |
| report_button | High | Outlook add-in, IT must deploy |
| sofie | High | Teams/Slack admin approval needed |
| human_risk_os | Medium | Needs data from other modules first |
| sso | High | SAML config, IT team required |
| scim | High | Entra ID/Okta integration, IT team required |

### Churn Mechanics

Churned accounts exhibit three synthetic signals:
1. **Lower activation probability** — 0.5x multiplier on feature activation
2. **Fewer campaigns** — campaign count halved
3. **Activity drop-off** — 60% of sessions skipped in the 30–60 days before churn date

## What to Observe

### After Step 1: Structured Data

```bash
# Verify tier distributions match config
sqlite3 data/sosafe.db "SELECT plan_tier, COUNT(*), ROUND(AVG(arr)), ROUND(AVG(churned),2) FROM accounts GROUP BY plan_tier"

# Check feature activation rates — high-difficulty features should be lower
sqlite3 data/sosafe.db "SELECT feature, ROUND(AVG(activated),2) as rate FROM feature_activations WHERE entitled=1 GROUP BY feature ORDER BY rate"

# Churned vs retained activation comparison — churned should be ~50% lower
sqlite3 data/sosafe.db "
  SELECT a.churned, f.feature, ROUND(AVG(f.activated),2) as rate
  FROM feature_activations f JOIN accounts a USING(account_id)
  WHERE f.entitled=1
  GROUP BY a.churned, f.feature
  ORDER BY f.feature, a.churned
"

# Event distribution — admin.login and admin.dashboard_viewed should dominate
sqlite3 data/sosafe.db "SELECT event_type, COUNT(*) as n FROM events GROUP BY event_type ORDER BY n DESC"
```

**What should stand out:**
- Essential tier has ~25% churn, Ultimate ~5% — 5x difference
- `report_button`, `sofie`, `sso`, `scim` activation rates should be 15–30% (high difficulty)
- `elearning`, `basic_phishing` should be 60–85% (low difficulty)
- Churned accounts activate features at roughly half the rate of retained accounts

### After Step 2: Unstructured Data

```bash
# Ticket category spread — should cover all 10 categories
sqlite3 data/sosafe.db "SELECT category, COUNT(*) FROM support_tickets GROUP BY category ORDER BY COUNT(*) DESC"

# Ticket priority by churn status — churned accounts should skew higher priority
sqlite3 data/sosafe.db "
  SELECT a.churned, t.priority, COUNT(*)
  FROM support_tickets t JOIN accounts a USING(account_id)
  GROUP BY a.churned, t.priority
"

# Transcript type distribution — 40% onboarding, 25% QBR, 20% escalation, 15% churn exit
sqlite3 data/sosafe.db "SELECT type, COUNT(*) FROM transcripts GROUP BY type"

# Review sentiment vs churn
sqlite3 data/sosafe.db "
  SELECT a.churned, r.sentiment, COUNT(*)
  FROM reviews r JOIN accounts a USING(account_id)
  GROUP BY a.churned, r.sentiment
"
```

**What should stand out:**
- Ticket subjects for churned accounts sound frustrated or mention setup failures
- Churn exit transcripts reference specific unactivated features
- Negative reviews correlate with churned accounts

### After Step 3: Graph

#### Interactive visualization

```bash
# All 200 accounts ↔ 8 features (green=retained, red=churned, blue=features)
python -m src.inspect_graph landscape

# One account's full neighborhood (features, campaigns, tickets, events)
python -m src.inspect_graph account ACC-0042

# Churned accounts only, with their features and tickets
python -m src.inspect_graph churn
```

Output goes to `graph/*.html`. Serve them with:
```bash
python -m http.server 8788 --directory graph
# open http://localhost:8788/landscape.html
```

Each view is interactive — pan, zoom, drag nodes, hover for tooltips (account profile, ticket subject/priority, event timestamps). Nodes settle after the physics simulation finishes.

| View | What it shows |
|------|---------------|
| `landscape` | All accounts connected to features. Churned accounts (red) cluster at edges with fewer green ACTIVATED lines. |
| `account` | One account's full subgraph: features (blue diamonds), campaigns (triangles), tickets (yellow squares), events (grey dots in temporal chain). |
| `churn` | Only churned accounts. Most connect to features via dashed lines only (entitled, never activated). Tickets radiate outward. |

#### Graph stats

The graph stats print automatically. Look for:
- **~65K nodes** (200 accounts + 8 features + ~4K campaigns + ~61K events + 500 tickets if step 2 ran)
- **~142K edges** without tickets, ~145K with tickets
- **ENTITLED_TO vs ACTIVATED gap** — there should be more ENTITLED_TO edges than ACTIVATED edges (the gap is the problem Tiago is investigating)

### After Step 5: Evaluation

The evaluation runs 5 questions through both GraphRAG and naive RAG:

| # | Question | What GraphRAG Should Win On |
|---|----------|-----------------------------|
| Q1 | Feature activation ↔ churn correlation | Aggregate activation rates across all 200 accounts with tier breakdowns |
| Q2 | Pre-churn behavioral signals | Temporal pattern analysis from event chains (NEXT edges) |
| Q3 | Essential vs Premium comparison | Structured cohort metrics (avg events, campaigns, activation rate, churn rate) |
| Q4 | Biggest activation gaps | Feature-level activation rates per tier from graph traversal |
| Q5 | Ticket ↔ churn correlation | Ticket category/priority aggregation by churn status (needs step 2 first) |

**What should stand out:**
- GraphRAG responses cite **3–5x more specific statistics** (percentages, counts, dollar amounts)
- GraphRAG references **specific features by name** with activation rates
- Naive RAG gives **qualitative summaries** of individual accounts it found via similarity search
- Q5 will show near-zero data for GraphRAG if you skip step 2 (no tickets in graph)

### The Core Demo Insight

The gap between ENTITLED_TO and ACTIVATED edges is the product insight Tiago cares about. GraphRAG can answer "which features have the lowest activation rate among churned Essential accounts" by traversing Account→Feature edges and filtering — naive RAG can only find similar-sounding account descriptions and hope the right ones surface.

## Architecture

```
src/
├── db.py                    # SQLite read/write utility
├── generate_sosafe.py       # Structured data (accounts, features, campaigns, events)
├── generate_unstructured.py # Claude-generated tickets, transcripts, reviews
├── build_graph.py           # NetworkX directed graph from SQLite
├── inspect_graph.py         # Interactive pyvis visualization (landscape, account, churn)
├── retrieval.py             # GraphRAG: traversal, aggregation, serialization
├── naive_rag.py             # FAISS + sentence-transformers baseline
├── llm.py                   # Claude API client (JourneyLLM class)
└── evaluate.py              # 5-question side-by-side comparison

data/
└── sosafe.db                # All structured + unstructured tables

graph/
├── sosafe_graph.pkl         # NetworkX DiGraph (pickled)
└── sosafe_naive_rag_index.pkl  # FAISS index + documents
```

## Reference

This implementation follows the patterns in `customer-journey-graphrag/` (e-commerce clickstream GraphRAG), adapted for B2B SaaS:
- `SEGMENTS` dict → `PLAN_TIERS` dict
- `session_to_document()` → `account_to_document()`
- `extract_user_journeys()` → `extract_account_journey()`
- `compare_cohorts()` → `compare_tiers()`
- `groq.Groq` → `anthropic.Anthropic`
- CSV files → SQLite database
