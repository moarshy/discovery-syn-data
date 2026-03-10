# Synthetic Data Generation Plan

**Jira:** KAN-60
**Owner:** Mohamed Arshath
**Reference repo:** `./customer-journey-graphrag/` ([GitHub](https://github.com/govind104/customer-journey-graphrag))
**Company profiles:** [sosafe.md](./sosafe.md) | [synthflow.md](./synthflow.md)

---

## Goal

Generate realistic synthetic B2B SaaS data for two demo organizations — **SoSafe** and **SynthFlow** — to power the Discovery product demo. The data must be good enough for Tiago (SoSafe PM) to validate on Tuesday's call, and realistic enough to prove that our context graph approach produces better synthesis than naive RAG.

---

## Architecture Overview

We fork the reference repo's approach but adapt it for B2B SaaS:

```
Reference Repo (e-commerce)          Our Version (B2B SaaS)
─────────────────────────             ──────────────────────
Users (segments)                  →   Accounts (plan tiers) + Tenants
Products (categories)             →   Features/Modules
Sessions (clickstream)            →   Admin sessions + End-user activity
Events (page_view, click, buy)    →   Feature events (activation, usage, churn signals)
                                  +   Unstructured: support tickets, transcripts, reviews
```

### Two Generation Methods

| Data Type | Method | Why |
|-----------|--------|-----|
| **Structured data** (accounts, subscriptions, events, usage metrics) | **Template-based** (Faker + NumPy + Pandas) | Fast, deterministic, controllable distributions — same approach as reference repo |
| **Unstructured data** (support tickets, customer transcripts, feature requests, reviews) | **LLM-generated** (Claude via Anthropic API) | Needs to read as realistic natural language when inspected record-by-record |

### LLM Provider

**Claude** (Anthropic API) — replacing Groq/Llama 3.1 from the reference repo. We already have `ANTHROPIC_API_KEY` in `.env` and it aligns with the product stack.

### Storage Format

**SQLite — one `.db` file per company** (e.g., `data/sosafe.db`, `data/synthflow.db`).

- Structured data lives in proper tables (accounts, features, events, campaigns, etc.)
- Unstructured data stored as text columns (support ticket bodies, transcript content, review text)
- Single portable file — easy to share, inspect with any SQLite client, and load into the graph builder
- Queryable — can run SQL to validate distributions, spot-check individual records, and power the "raw data drill-down" that Tiago demanded
- Graph builder reads from SQLite instead of CSVs

```
data/
├── sosafe.db        # All SoSafe tables + text data
└── synthflow.db     # All SynthFlow tables + text data
```

---

## Phase 1: Structured Data Generation

### SoSafe Data Schema

Generate data that mirrors what Tiago actually works with.

#### 1.1 Accounts (Salesforce-like) — 200 accounts

| Field | Type | Distribution |
|-------|------|-------------|
| account_id | int | Sequential |
| name | str | Faker company name |
| industry | str | Weighted: Automotive 15%, Telecom 10%, Finance 15%, Manufacturing 15%, Healthcare 10%, Retail 10%, IT 10%, Government 10%, Other 5% |
| employee_count | int | Log-normal: median ~2,000 |
| country | str | Weighted: Germany 40%, UK 15%, Austria 10%, Switzerland 10%, Netherlands 5%, Nordics 10%, Other 10% |
| plan_tier | str | Essential 20%, Professional 40%, Premium 30%, Ultimate 10% |
| arr | float | Essential: $5-15K, Professional: $15-40K, Premium: $40-80K, Ultimate: $80-200K |
| seats_licensed | int | Correlated with employee_count (10-100% coverage) |
| seats_active | int | 60-95% of licensed (varies by segment health) |
| contract_start | date | Random within last 24 months |
| contract_end | date | Start + 12 months |
| csm_assigned | str | Faker name |
| onboarding_completed | bool | 85% True |
| churned | bool | Essential: 25%, Professional: 15%, Premium: 8%, Ultimate: 3% |
| churn_date | date | If churned, within contract period |

#### 1.2 Features/Modules (replaces "Products") — 8 features

| feature_id | name | plan_required | activation_difficulty |
|------------|------|---------------|----------------------|
| 1 | E-Learning Platform | Essential | Low |
| 2 | Phishing Simulations | Essential | Low |
| 3 | Analytics Dashboard | Professional | Low |
| 4 | Phishing Report Button | Professional | High (IT dependency) |
| 5 | SCIM Provisioning | Professional | High (IT dependency) |
| 6 | SSO/SAML | Professional | High (IT dependency) |
| 7 | Sofie AI Copilot | Premium | Medium (Teams/Slack admin) |
| 8 | Human Risk OS | Premium | Medium (needs data from other modules) |

#### 1.3 Feature Activations — per account

| Field | Type | Notes |
|-------|------|-------|
| account_id | int | FK |
| feature_id | int | FK |
| entitled | bool | Based on plan_tier |
| activated | bool | Based on activation_difficulty + health |
| activation_date | date | Days after contract_start (varies) |
| days_to_activate | int | Derived |
| usage_frequency | str | daily/weekly/monthly/inactive |

**Key pattern:** Premium/Ultimate accounts that DON'T activate Sofie or Report Button → high churn correlation (this is Tiago's core analysis).

#### 1.4 Events (Mixpanel-like) — ~50K events

| Field | Type | Values |
|-------|------|--------|
| event_id | int | Sequential |
| account_id | int | FK |
| user_type | str | admin / end_user |
| event_type | str | See event taxonomy below |
| timestamp | datetime | Sequential within sessions |
| feature_area | str | Which module |
| metadata | json | Event-specific data |

**Admin Event Types:**
- `admin.login`, `admin.dashboard_viewed`, `admin.campaign_created`, `admin.campaign_launched`
- `admin.user_imported`, `admin.report_exported`, `admin.settings_changed`
- `feature.report_button_installed`, `feature.sofie_deployed`, `feature.scim_configured`, `feature.sso_configured`
- `onboarding.step_completed`, `onboarding.completed`

**Simulation Event Types:**
- `simulation.email_sent`, `simulation.email_opened`, `simulation.link_clicked`
- `simulation.data_entered`, `simulation.email_reported`

**E-Learning Event Types:**
- `elearning.module_assigned`, `elearning.module_started`, `elearning.module_completed`

**Behavioral Patterns to Encode:**
- Healthy accounts: high admin login frequency → campaigns launched → declining click rates → rising report rates
- At-risk accounts: low admin login → no campaigns after initial setup → features not activated → churn
- Churned accounts: activity drops sharply 30-60 days before churn date

#### 1.5 Campaign Results — per campaign

| Field | Type | Notes |
|-------|------|-------|
| campaign_id | int | Sequential |
| account_id | int | FK |
| type | str | phishing / elearning |
| launch_date | date | |
| target_count | int | Subset of active seats |
| emails_sent | int | ~target_count |
| emails_opened | int | 60-80% |
| links_clicked | int | Healthy: 5-15%, New: 20-40% |
| data_entered | int | 30-50% of clicked |
| emails_reported | int | If Report Button active: 20-50% |
| modules_completed | int | For elearning: 70-97% |

### SynthFlow Data Schema

#### 1.6 Accounts — 300 accounts

| Field | Type | Distribution |
|-------|------|-------------|
| account_id | int | Sequential |
| name | str | Faker company name |
| industry | str | Healthcare 20%, Real Estate 15%, Insurance 15%, BPO 15%, E-commerce 10%, Finance 10%, Technology 10%, Other 5% |
| plan_type | str | PAYG 50%, Enterprise 30%, Agency 20% |
| mrr | float | PAYG: $50-500, Enterprise: $2.5K-10K, Agency: $1K-5K |
| signup_date | date | Random within last 18 months |
| churned | bool | PAYG: 35%, Enterprise: 8%, Agency: 15% |
| agents_deployed | int | PAYG: 1-3, Enterprise: 5-40, Agency: 10-100 |

#### 1.7 Agents — ~1,500 agents

| Field | Type | Notes |
|-------|------|-------|
| agent_id | int | Sequential |
| account_id | int | FK |
| name | str | e.g., "Appointment Scheduler", "Lead Qualifier" |
| type | str | flow (60%) / prompt (40%) |
| use_case | str | appointment/lead_qual/support/ivr/outbound |
| language | str | English 60%, Spanish 15%, German 10%, Other 15% |
| llm_provider | str | openai 50%, anthropic 20%, azure 15%, custom 15% |
| knowledge_base_size | int | 0-500 docs |
| created_at | date | After account signup |
| is_active | bool | |
| last_call_date | date | |

#### 1.8 Calls — ~100K calls

| Field | Type | Notes |
|-------|------|-------|
| call_id | int | Sequential |
| agent_id | int | FK |
| account_id | int | FK |
| direction | str | inbound 60% / outbound 40% |
| duration_seconds | int | 30-600s |
| timestamp | datetime | |
| resolution | str | resolved 65% / transferred 20% / abandoned 15% |
| sentiment_score | float | 0.0-1.0 |
| latency_ms | int | 80-500ms |

---

## Phase 2: Unstructured Data Generation (LLM)

Use Claude to generate realistic text data. Each type gets a specialized prompt with company context.

### 2.1 Support Tickets — 500 per company

**Generation approach:** Batch-generate using Claude with a prompt that includes:
- Company context (from sosafe.md / synthflow.md)
- Ticket category distribution
- Account context (plan tier, features activated, health signals)
- Realistic subject lines and body text

**SoSafe ticket categories:**
| Category | % | Example |
|----------|---|---------|
| Email Delivery / Whitelisting | 20% | "Phishing sims going to spam in Outlook 365" |
| SCIM / User Provisioning | 15% | "New hires not syncing from Entra ID" |
| SSO / Authentication | 10% | "SAML SSO returning 403 for some users" |
| Report Button Issues | 10% | "Add-in not appearing in Outlook desktop" |
| Campaign Configuration | 15% | "Need help setting up department-specific campaigns" |
| Analytics / Reporting | 10% | "Dashboard not reflecting latest campaign results" |
| Content / Courses | 10% | "Need cybersecurity training in Portuguese" |
| Billing / Licensing | 5% | "Need to add 200 seats mid-contract" |
| Sofie / AI Copilot | 5% | "Sofie not responding in Teams channel" |

**SynthFlow ticket categories:**
| Category | % | Example |
|----------|---|---------|
| Agent Setup / Configuration | 20% | "Agent not handling edge case in appointment flow" |
| Call Quality / Latency | 15% | "Callers report delayed responses after 2pm" |
| Integration Issues | 15% | "HubSpot webhook not triggering after call ends" |
| Telephony / Numbers | 10% | "Need to port existing toll-free number" |
| Billing / Usage | 10% | "Unexpected overage charges this month" |
| Knowledge Base / RAG | 10% | "Agent giving wrong answers about pricing" |
| API / Webhooks | 10% | "POST to /calls endpoint returning 500" |
| Feature Requests | 5% | "Need ability to schedule outbound campaigns by timezone" |
| Compliance | 5% | "Need HIPAA BAA for healthcare deployment" |

### 2.2 Customer Transcripts — 50 per company

Types: onboarding calls, QBR reviews, escalation calls, churn exit interviews.
Generate with Claude using account context to make them specific.

### 2.3 Feature Requests / Reviews — 100 per company

NPS responses, G2-style reviews, ProductBoard-style feature requests.
Sentiment distribution: 30% positive, 45% neutral, 25% negative.

### 2.4 Churn Reasons — for each churned account

Brief narrative explaining why the account churned, tied to the account's actual data signals.

---

## Phase 3: Graph Construction

Adapt `build_graph.py` for B2B SaaS entities.

### Graph Schema

```
Account ──SUBSCRIBES_TO──→ Plan
Account ──HAS_TENANT──→ Tenant
Account ──FILED──→ Support Ticket
Tenant ──ENTITLED_TO──→ Feature
Tenant ──ACTIVATED──→ Feature
Tenant ──RAN──→ Campaign
Admin ──PERFORMED──→ Event
Event ──NEXT──→ Event (temporal chain)
Event ──INVOLVES──→ Feature
Campaign ──PRODUCED──→ Campaign Result
Support Ticket ──RELATES_TO──→ Feature
```

### Node Types

| Type | Count (SoSafe) | Key Attributes |
|------|----------------|----------------|
| Account | 200 | plan_tier, arr, churned, industry |
| Feature | 8 | name, plan_required, activation_difficulty |
| Event | ~50K | event_type, timestamp, feature_area |
| Campaign | ~2K | type, launch_date, target_count |
| Support Ticket | 500 | category, priority, status |
| Transcript | 50 | type, sentiment |

---

## Phase 4: Evaluation

Adapt `retrieval.py` and `naive_rag.py` to compare approaches using B2B SaaS questions.

### Evaluation Questions (SoSafe)

1. "Why are Premium customers failing to activate the Phishing Report Button?"
2. "What's the typical admin behavior pattern before churn?"
3. "How do Enterprise accounts' phishing click rates compare to Mid-Market?"
4. "Which features have the highest activation gap between entitled and activated?"
5. "What support ticket patterns correlate with accounts that churn within 90 days?"

### Evaluation Questions (SynthFlow)

1. "Why do PAYG accounts fail to convert to Enterprise?"
2. "What's the typical journey from signup to first production call?"
3. "Which integrations correlate with higher retention?"
4. "How does call quality (sentiment, resolution) differ between healthcare and BPO accounts?"
5. "What support patterns appear in accounts with declining call minutes?"

### Comparison Framework

Same as reference repo: run each question through both GraphRAG and naive RAG, compare:
- Number of specific statistics cited
- Path/pattern identification quality
- Actionability of insights
- Response time

---

## Phase 5: Validation

### Self-Validation (before Tuesday call)

- [ ] Aggregate distributions match expectations (churn rates, activation rates, event volumes)
- [ ] Individual support tickets read as realistic
- [ ] Feature activation correlates with churn as expected
- [ ] Graph queries return meaningful path patterns
- [ ] GraphRAG produces quantitatively better answers than naive RAG

### Tiago Validation (Tuesday call)

- [ ] Does the SoSafe data schema match his mental model?
- [ ] Do the event types cover his Mixpanel events?
- [ ] Are the activation patterns realistic?
- [ ] Do the support ticket categories feel right?
- [ ] Would he use this data to demo to his boss?

---

## Execution Order

```
Step 1: Generate structured data (accounts, features, events, campaigns)
        ├── SoSafe: generate_sosafe.py
        └── SynthFlow: generate_synthflow.py

Step 2: Generate unstructured data (support tickets, transcripts, reviews)
        ├── Uses Claude API
        └── Conditioned on structured data (account context)

Step 3: Build knowledge graphs
        └── Adapted build_graph.py

Step 4: Build naive RAG index
        └── Adapted naive_rag.py

Step 5: Run evaluation
        └── Compare GraphRAG vs naive RAG on B2B SaaS questions

Step 6: Validate
        ├── Self-check distributions and outputs
        └── Tiago review on Tuesday
```

---

## File Structure

```
round2/synthetic-data-gen/
├── customer-journey-graphrag/     # Reference repo (read-only)
├── docs/
│   ├── plan.md                    # This file
│   ├── sosafe.md                  # SoSafe product research
│   └── synthflow.md               # SynthFlow product research
├── src/
│   ├── generate_sosafe.py         # SoSafe structured data generator
│   ├── generate_synthflow.py      # SynthFlow structured data generator
│   ├── generate_unstructured.py   # LLM-powered unstructured data generator
│   ├── build_graph.py             # Adapted graph construction
│   ├── retrieval.py               # Adapted GraphRAG retrieval
│   ├── naive_rag.py               # Adapted naive RAG baseline
│   ├── llm.py                     # Claude integration (replaces Groq)
│   ├── evaluate.py                # Side-by-side comparison runner
│   └── api.py                     # FastAPI endpoints
├── data/
│   ├── sosafe.db                  # All SoSafe tables + text (SQLite)
│   └── synthflow.db               # All SynthFlow tables + text (SQLite)
├── graph/
│   ├── sosafe_graph.pkl           # SoSafe knowledge graph
│   └── synthflow_graph.pkl        # SynthFlow knowledge graph
├── pyproject.toml
├── .env                           # ANTHROPIC_API_KEY
└── README.md
```

---

## Dependencies

```
# Core (same as reference repo)
networkx>=3.2
pandas>=2.1
numpy>=1.26
faker>=22.0
faiss-cpu>=1.7
sentence-transformers>=2.2
fastapi>=0.109
uvicorn>=0.25
streamlit>=1.30
httpx>=0.26
python-dotenv>=1.0

# Changed from reference repo
anthropic>=0.40       # Replaces groq (for Claude API)

# New
tqdm>=4.66            # Progress bars for LLM generation
```
