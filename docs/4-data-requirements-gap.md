# SoSafe Data Requirements — Coverage Report

Source: Jira ticket [KAN-60](https://naptha.atlassian.net/browse/KAN-60) — Tiago's WhatsApp message with SoSafe data schema.

Last updated: 2026-03-10 — all gaps from the original analysis are now closed.

---

## Tiago's Data Requirements

### Structured Data — Commercial

| # | Object | Description |
|---|--------|-------------|
| 1 | **account** | Firmographics — company info, industry, size, region |
| 2 | **subscription** | Over-time view of what they pay and what they get (plan history, ARR changes, renewal/upgrade/downgrade events) |

### Structured Data — Product Usage

| # | Object | Description |
|---|--------|-------------|
| 3 | **tenant** | Workspace/environment object — deployment config, user limits, setup state |
| 4 | **campaign** | Phishing simulations and e-learning campaigns |
| 5 | **user** | Individual users within an account — admins, end users, managers |
| 6 | **campaign activity** | Per-campaign events — emails sent, opened, clicked, reported, modules completed |
| 7 | **admin user activity** | Admin-level actions — logins, dashboard views, campaign creation, settings changes |
| 8 | **end user activity** | End-user actions — simulation interactions, e-learning progress, report button usage |

### Unstructured Data

| # | Object | Description |
|---|--------|-------------|
| 9 | **support tickets** | Zendesk/Intercom-style tickets with category, priority, resolution |
| 10 | **customer transcripts** | Call transcripts — onboarding, QBRs, escalations, churn exits |
| 11 | **feature requests (ProductBoard)** | Product feature requests with votes, status, customer context |
| 12 | **churn reasons (Salesforce)** | Churn exit narratives with reason categories |

---

## Current State

All 12 requirements are covered. The pipeline generates structured data deterministically (seeded RNGs) and unstructured data via Claude API calls with batched concurrency.

### Structured Tables in `sosafe.db`

| Table | Rows | Key Columns |
|-------|------|-------------|
| `accounts` | 200 | account_id, name, industry, employee_count, country, plan_tier, arr, contract_start, contract_end, churned, churn_date, csm_assigned |
| `subscriptions` | 534 | subscription_id, account_id, plan_tier, mrr, arr, start_date, end_date, change_type, seats, modules |
| `feature_activations` | 1,600 | account_id, feature, entitled, activated, activation_date |
| `tenants` | 200 | tenant_id, account_id, domain, created_at, sso_enabled, scim_enabled, report_button_deployed, sofie_enabled, user_limit, active_users, setup_completion, environment |
| `users` | 7,684 | user_id, account_id, tenant_id, name, email, role, department, created_at, last_active, status |
| `campaigns` | 4,062 | campaign_id, account_id, type, launch_date, target_count, status |
| `events` | 416,637 | event_id, account_id, user_id, event_type, timestamp, campaign_id |

### Unstructured Tables in `sosafe.db`

| Table | Rows | Key Columns |
|-------|------|-------------|
| `support_tickets` | 500 | ticket_id, account_id, category, subject, body, priority, status, created_at, resolved_at |
| `transcripts` | 49 | transcript_id, account_id, type, date, content, summary |
| `reviews` | 100 | review_id, account_id, rating, title, body, sentiment, date |
| `churn_reasons` | 31 | reason_id, account_id, churn_date, reason_category, notes |
| `feature_requests` | 240 | request_id, account_id, user_id, title, description, category, priority, status, votes, submitted_at, updated_at |

### Event Types

All admin and campaign events now carry a `user_id` FK. Each row represents one user's action (no aggregate `count` column).

**Admin events** (attributed to admin/manager users):
- `admin.login` — 18,224 rows
- `admin.dashboard_viewed` — 18,224 rows
- `admin.campaign_created` — 5,554 rows
- `admin.campaign_launched` — 3,894 rows

**Simulation events** (per-user funnel, attributed to end users):
- `simulation.email_sent` — 92,869 rows
- `simulation.email_opened` — 55,871 rows
- `simulation.link_clicked` — 8,508 rows
- `simulation.data_entered` — 2,190 rows
- `simulation.email_reported` — 4,604 rows

**E-learning events** (per-user funnel, attributed to end users):
- `elearning.module_assigned` — 96,516 rows
- `elearning.module_started` — 67,555 rows
- `elearning.module_completed` — 42,132 rows

**Feature events** (system-level, no user_id):
- `feature.{name}_activated` — 496 rows total

### Key Distributions

**Users:** admin 7.0%, manager 14.7%, end_user 78.4% (target: ~5/15/80)

**Subscriptions:** initial 200, renewal 242, upgrade 46, downgrade 15, churned 31

**Tenants:** production 181, staging 14, sandbox 5

**Feature requests:** under_review 98, planned 49, in_progress 43, declined 26, completed 24

---

## Requirement ↔ Table Mapping

| # | Requirement | Table | Status | Notes |
|---|-------------|-------|--------|-------|
| 1 | account | `accounts` | COVERED | 200 accounts across 4 tiers (Essential/Professional/Premium/Ultimate) |
| 2 | subscription | `subscriptions` | COVERED | 534 rows — initial, renewal, upgrade, downgrade, churned events per account |
| 3 | tenant | `tenants` | COVERED | 200 rows — 1:1 with accounts, feature flags derived from activations, domain/environment/setup |
| 4 | campaign | `campaigns` | COVERED | 4,062 phishing simulation + e-learning campaigns |
| 5 | user | `users` | COVERED | 7,684 users with role/department/status, linked to accounts and tenants |
| 6 | campaign activity | `events` | COVERED | Per-user simulation and e-learning funnel events tied to campaigns and users |
| 7 | admin user activity | `events` | COVERED | Admin login/dashboard/campaign events attributed to admin/manager users |
| 8 | end user activity | `events` | COVERED | Simulation + e-learning events attributed to individual end users |
| 9 | support tickets | `support_tickets` | COVERED | 500 Claude-generated tickets |
| 10 | customer transcripts | `transcripts` | COVERED | 49 Claude-generated call transcripts (onboarding, QBR, escalation, churn exit) |
| 11 | feature requests | `feature_requests` | COVERED | 240 Claude-generated ProductBoard-style requests with votes, status, categories |
| 12 | churn reasons | `churn_reasons` | COVERED | 31 churned account exit narratives with reason categories |

---

## Graph Coverage

The `build_graph.py` pipeline constructs a NetworkX DiGraph with:

**Node types (9):** Account, Feature, Campaign, Event, Ticket, Tenant, User, Subscription, FeatureRequest

**Edge types (14):**

| Edge | From → To | Count | Semantics |
|------|-----------|-------|-----------|
| GENERATED | Account → Event | 416,637 | Account produced event |
| NEXT | Event → Event | 416,437 | Temporal chain |
| PRODUCED | Campaign → Event | 370,245 | Campaign produced event |
| ENTITLED_TO | Account → Feature | 340 | Feature entitlement |
| ACTIVATED | Account → Feature | 496 | Feature activated |
| RAN | Account → Campaign | 4,062 | Account ran campaign |
| FILED | Account → Ticket | 500 | Account filed ticket |
| RELATES_TO | Ticket/FR → Feature | 844 | Category→feature mapping |
| HAS_TENANT | Account → Tenant | 200 | Workspace ownership |
| BELONGS_TO | User → Account | 7,684 | User membership |
| WORKS_IN | User → Tenant | 7,684 | User workspace |
| SUBSCRIBED | Account → Subscription | 534 | Plan history |
| REQUESTED_BY | Account → FeatureRequest | 240 | Account filed request |
| SUBMITTED | User → FeatureRequest | 240 | User submitted request |

**Totals:** 430,065 nodes / 1,226,143 edges

---

## Downstream Pipeline Impact

| Component | Status | Notes |
|-----------|--------|-------|
| `generate_sosafe.py` | Updated | Subscriptions, tenants, users generators added. Events refactored to per-user rows. |
| `generate_synthflow.py` | Updated | Mirrored all changes with SynthFlow-specific constants and seeds (43_00x). |
| `generate_unstructured.py` | Updated | Feature requests generator added (batch-10 pattern, Claude API). |
| `build_graph.py` | Updated | 5 new node types, 7 new edge types, safe loading for optional tables. |
| `retrieval.py` | Needs update | Traversal patterns should be updated for User/Tenant/Subscription/FeatureRequest nodes. |
| `naive_rag.py` | Needs update | Re-index with new tables (users, tenants, subscriptions, feature_requests). |
| `evaluate.py` | Needs update | Add evaluation questions covering new data dimensions (user-level queries, subscription history, feature requests). |
