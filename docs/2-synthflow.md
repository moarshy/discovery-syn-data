# SynthFlow AI — Product Research for Synthetic Data Generation

## What SynthFlow Does

SynthFlow AI is a **no-code AI voice agent platform** (HQ: Berlin, Germany) that automates inbound and outbound phone calls using conversational AI. Businesses deploy voice agents that conduct real phone conversations — handling appointment scheduling, lead qualification, customer support, and call routing.

- Founded 2023, $30M total funding (Series A led by Accel)
- 65M+ calls handled, 4-5M+ hours saved, 1,000+ customers
- 99.99% uptime, sub-100ms latency (proprietary telephony stack)
- SOC 2, HIPAA, PCI DSS, GDPR, ISO 27001 compliant
- 30-40+ languages supported

---

## Product Modules

### 1. Agent Builder
- **Flow Designer:** Visual drag-and-drop workflow editor (nodes: Greeting, Conversation, Branch, Call Transfer, Real-Time Booking, Custom Action, End Call)
- **Single-Prompt Agents:** LLM-driven agents configured via natural language
- **Voice Configuration:** Voice selection, speed, volume, cloning, multilingual
- **Knowledge Base / RAG:** Upload docs/FAQs for agent to reference
- **Information Extractors:** Structured data collection during calls
- **Custom Actions:** Trigger external APIs mid-conversation

### 2. Call Management
- Inbound call handling (24/7 AI receptionist)
- Outbound campaigns (automated dialing for leads, surveys, reminders)
- AI IVR (conversational menu replacement)
- Call transfer / warm handoff to humans
- Voicemail detection
- Concurrent call scaling

### 3. Telephony
- Synthflow Native Telephony (Enterprise — proprietary stack)
- Synthflow-Managed Twilio ($0.02/min)
- Bring Your Own Twilio ($0.00/min)
- SIP/PBX connectivity (RingCentral, Dialpad, Telnyx, Vonage)

### 4. Testing & QA
- **Test Center:** Simulated calls to measure accuracy and compliance
- **Auto-QA:** Analyzes live conversations for accuracy, intent matching, compliance
- **Version Control:** Track agent versions and rollback

### 5. Analytics
- Full call transcripts and recordings
- Performance metrics: duration, resolution rate, sentiment, latency
- Conversation analytics: sentiment, intent detection, topic clustering
- Real-time monitoring dashboard

### 6. Agency / White-Label
- Custom branding (logo, colors, domain)
- Subaccount management for client accounts
- Custom pricing / rebilling
- GoHighLevel integration

---

## User Types

| Type | Description |
|------|-------------|
| Operations/CX Leader | Strategic deployment, ROI tracking, scaling decisions |
| Business User/Admin | Day-to-day agent config, monitoring dashboards |
| Agent Builder/Designer | Uses Flow Designer or Single-Prompt to build agents |
| Developer/Integrator | API integration, webhooks, custom actions, LLM config |
| Agency Owner/Reseller | White-labels platform, manages subaccounts |
| QA/Compliance Analyst | Test Center, Auto-QA, transcript review |

---

## Customer Segments

| Segment | Characteristics |
|---------|----------------|
| Enterprise | 10,000+ min/month, custom telephony, dedicated support, $30K-$100K+/yr |
| Mid-Market | 1,000-10,000 min/month, CRM integrations, moderate compliance |
| SMB | <1,000 min/month, PAYG, basic use cases |
| Agencies | White-label resellers, multiple client accounts |

**Industries:** Healthcare, real estate, insurance, financial services, e-commerce, BPO/call centers, retail, technology

**Case studies:**
- Medbelle (Healthcare): 60% boost in scheduling efficiency, 2.5x more bookings
- $230M BPO: 40+ agents in 60 days, 600K+ calls/month automated

---

## Pricing

| Plan | Target | Pricing |
|------|--------|---------|
| Pay As You Go | Builders, pilots | Usage-based ($0.15-$0.24/min all-in) |
| Enterprise | 10,000+ min/month | Custom pricing |
| Agency | Resellers | 6,000 min included, $0.15/min overage |

**Per-minute breakdown (PAYG):**
- Voice Engine: $0.09/min
- GPT-4.1 mini: $0.02/min
- Bring Your Own LLM: $0.00/min
- Managed Twilio: $0.02/min

---

## Key Metrics a PM Would Track

### Adoption & Growth
| Metric | Description |
|--------|-------------|
| Active Agents Deployed | Number of voice agents in production |
| Total Call Minutes | Monthly call volume (core billing unit) |
| New Agent Creations | Product engagement signal |
| Integration Activation Rate | % connecting CRM, telephony, calendar |
| Feature Adoption by Module | % using Knowledge Base, Call Transfer, Auto-QA |
| Time to First Agent Live | Days from signup to first production call |

### Usage & Engagement
| Metric | Description |
|--------|-------------|
| Minutes per Account (Monthly) | Consumption — key revenue driver |
| Concurrent Call Peak | Capacity planning |
| API Call Volume | Developer engagement |
| Test Center Usage | Quality investment signal |
| Agent Edit Frequency | Active tuning signal |

### Quality & Performance
| Metric | Description |
|--------|-------------|
| Call Resolution Rate | % resolved without human handoff |
| Human Handoff Rate | % transferred to humans |
| Sentiment Score Distribution | Positive/neutral/negative |
| Latency (p50, p95, p99) | Voice response time |
| Auto-QA Pass Rate | % meeting quality thresholds |

### Revenue
| Metric | Description |
|--------|-------------|
| MRR/ARR | Revenue |
| Net Revenue Retention (NRR) | Expansion vs contraction |
| Minutes Growth Rate | MoM consumption growth |
| PAYG to Enterprise Conversion | Upgrade funnel |

---

## Integrations

- **CRM:** Salesforce, HubSpot, Pipedrive, ActiveCampaign, Zoho, Freshworks
- **Telephony:** Twilio, Five9, RingCentral, Avaya, Genesys, 8x8, Dialpad
- **Healthcare:** AthenaOne, Dentrix
- **Calendar:** Google Calendar, Microsoft Calendar, Cal.com
- **Automation:** Zapier, Make, n8n
- **AI/LLM:** OpenAI, Anthropic, ElevenLabs, Azure
- **Support:** Zendesk, Intercom
- **Agency:** GoHighLevel

---

## Churn Signals

**Usage-based (strongest):**
- Declining call minutes month-over-month
- Agent going inactive (no calls 7+ days)
- No new agent creations in 30+ days
- Concurrent calls consistently at 1 (never scaled beyond pilot)

**Engagement:**
- Declining dashboard logins
- No Knowledge Base updates in 30+ days
- No agent edits in 30+ days
- Test Center unused

**Quality:**
- Rising human handoff rate
- Declining sentiment scores
- Increasing call duration without resolution
- Latency spikes

**Support:**
- Spike in support tickets
- Tickets about billing/cancellation
- Negative CSAT scores

---

## Synthetic Data Schema (for KAN-60)

### Structured Data — Commercial (Salesforce-like)
- **Account:** account_id, name, industry, employee_count, country, plan_type (payg/enterprise/agency), mrr, signup_date, churned, churn_date
- **Subscription:** subscription_id, account_id, plan_type, included_minutes, overage_rate, add_ons[], start_date, billing_cycle

### Structured Data — Product Usage
- **Agent:** agent_id, account_id, name, type (flow/prompt), language, voice_id, llm_provider, knowledge_base_size, created_at, is_active, last_call_date
- **Call:** call_id, agent_id, account_id, direction (inbound/outbound), duration_seconds, timestamp, resolution (resolved/transferred/abandoned), sentiment_score, latency_ms, voicemail_detected
- **Integration:** integration_id, account_id, type (crm/telephony/calendar/automation), provider, connected_at, last_sync, is_active
- **Admin Activity:** activity_id, account_id, user_id, action (agent_created/agent_edited/kb_updated/test_run/dashboard_viewed), timestamp

### Unstructured Data
- **Support Tickets:** ticket_id, account_id, category (setup/integration/call_quality/billing/feature_request/latency/compliance), subject, body, priority, status, created_at, resolved_at
- **Call Transcripts:** transcript_id, call_id, content, summary, extracted_data{}
- **Customer Reviews:** review_id, account_id, platform (g2/trustpilot/gartner), rating, pros, cons, date
- **CS Notes:** note_id, account_id, type (check_in/expansion/risk_flag/competitive_mention), content, date
- **NPS/CSAT Responses:** response_id, account_id, score, feedback_text, date
