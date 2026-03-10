# SoSafe — Product Research for Synthetic Data Generation

## What SoSafe Does

SoSafe is a European **cybersecurity awareness and human risk management platform** (HQ: Cologne, Germany). It helps organizations reduce human-related security risk through personalized, behavior-based training and phishing simulations.

- 3,000+ organizations, 5.4M+ users
- Phishing click rates reduced by up to 70% after one year
- Available in 33 languages
- Enterprise-grade deployment in as little as 2 days

---

## Product Modules

### 1. E-Learning / Security Awareness Training
- Personalized, gamified, story-based micro-learning modules (31+ modules)
- Topics: phishing, social engineering, password security, AI literacy, data privacy, GDPR
- Adaptive learning paths based on role, department, and performance
- SCORM support for embedding in customer LMS

### 2. Phishing Simulations
- 68+ phishing simulation templates
- Adaptive difficulty engine (adjusts based on user performance)
- Instant in-the-moment learning when user clicks a simulated phish
- Simulation Studio: AI-assisted custom phishing template creation

### 3. Phishing Report Button
- Outlook add-in for employees to report suspicious emails
- Integrates with SOC workflows (Jira, ServiceNow)
- 188% increase in reporting rates after adoption

### 4. Sofie — AI Copilot
- Conversational AI in Microsoft Teams and Slack
- Real-time security alerts and nudges
- Answers employee security questions on demand

### 5. Human Risk OS (Platform Dashboard)
- **Human Security Index (HSI):** composite risk score across:
  - Awareness (training interactions, quiz scores)
  - Behavior (phishing responses, real-world actions)
  - Culture (survey responses, engagement patterns)
- Predictive risk scoring for high-risk user groups
- Compliance dashboards for ISO 27001, GDPR, DORA, NIS2, TISAX, HIPAA

---

## Key Metrics (Dashboard)

| Metric | Definition |
|--------|-----------|
| Click Rate | % of phishing emails where user clicked |
| Open Rate | % of emails where tracking pixel loaded |
| Interaction Rate | % who engaged with phishing landing page |
| Reply Rate | % who replied to phishing email |
| Reporting Rate | % who reported via Phishing Report Button |
| Learning Rate | % who engaged with learning page after phishing |
| E-Learning Completion Rate | % of assigned modules completed |
| Registration Rate | % of provisioned users who logged in |
| Human Security Index (HSI) | Composite score (0-100) |

---

## User Types

| Type | Description |
|------|-------------|
| Full Rights Admin | Manages campaigns, users, analytics, settings |
| Analytics Admin | Read-only access to dashboards and reports |
| End User (Employee) | Receives phishing sims, completes training, uses Report Button |
| Manager/Executive | Consumes executive risk dashboards |
| Partner/MSP Admin | Manages multiple client accounts |

---

## Customer Segments

- **Primary:** Mid-market and large enterprises in Europe (DACH region)
- **Expanding:** UK, Nordics, North America
- **Industries:** Automotive (KIA), Telecom (Vodafone), Retail (Aldi Nord), Finance, Manufacturing, Government, Healthcare
- **Buyers:** CISO, IT Security Manager, Compliance Officer, HR/L&D

---

## Pricing Tiers

| Plan | Target | Key Inclusions |
|------|--------|---------------|
| Essential | SMB | Core e-learning, basic phishing sims, standard analytics |
| Professional | Mid-market | Expanded library, advanced campaigns, Report Button |
| Premium | Enterprise | Sofie AI copilot, Human Risk OS, custom content |
| Ultimate | Large Enterprise | Full access, advanced API, dedicated CSM |

---

## Integrations

- **Identity:** Microsoft Entra ID, Okta, Google Workspace, SAP SuccessFactors, Personio
- **Communication:** Microsoft Teams, Slack, Outlook
- **ITSM:** Jira Service Management, ServiceNow
- **LMS:** SCORM streaming
- **Analytics:** PowerBI, Phishing API

---

## Tiago's Use Case: Feature Activation Analysis

Tiago is a Product/Growth Analyst. His core question: **"Why do customers fail to activate features after purchase?"**

### Data Sources He Uses

| Source | What He Gets |
|--------|-------------|
| Mixpanel | Feature activation events, user journeys, funnel analysis |
| Salesforce | Deal size, plan tier, contract dates, ARR, CSM notes |
| Support Tickets | Qualitative signal on blockers and friction |

### His Analysis Loop
1. Identify features with low activation rates
2. Segment by customer attributes (industry, size, plan tier)
3. Correlate activation gaps with churn outcomes
4. Investigate root causes via support tickets
5. Recommend interventions

### Realistic Mixpanel Events
- `admin.login`, `admin.dashboard_viewed`, `admin.campaign_created`, `admin.campaign_launched`
- `feature.report_button_installed`, `feature.sofie_deployed`, `feature.scim_configured`, `feature.sso_configured`
- `simulation.email_sent`, `simulation.email_opened`, `simulation.link_clicked`, `simulation.data_entered`, `simulation.email_reported`
- `elearning.module_assigned`, `elearning.module_started`, `elearning.module_completed`
- `onboarding.step_completed`, `onboarding.completed`

### Feature Activation Gaps (Churn Risk)

| Feature | Activation Challenge |
|---------|---------------------|
| Phishing Report Button | Requires Outlook add-in deployment — IT dependency |
| Sofie (AI Copilot) | Requires Teams/Slack admin approval |
| SCIM Provisioning | Requires Entra ID/Okta integration — IT dependency |
| Human Risk OS | Needs sufficient data from other modules |
| SSO | Requires IT team SAML configuration |

---

## Churn Signals

- Feature non-activation after purchase (bought Premium but never deployed Sofie/Report Button)
- Zero phishing campaigns in 90+ days
- Low admin login frequency
- Declining e-learning completion rates
- Seat utilization below 50%
- Spike in support tickets
- No SSO/SCIM configured
- Champion departure (CISO/IT Security Manager leaves)

---

## Competitive Landscape

| Competitor | Positioning |
|-----------|-------------|
| KnowBe4 | Market leader, broadest content library |
| Proofpoint | Enterprise email security ecosystem |
| Hoxhunt | Gamified behavior change |
| Cofense | Phishing detection & response |
| Adaptive Security | AI-native, deepfake/voice phishing focus |

---

## Synthetic Data Schema (for KAN-60)

### Structured Data — Commercial (Salesforce-like)
- **Account:** account_id, name, industry, employee_count, country, plan_tier, arr, contract_start, contract_end, csm_assigned, churned
- **Subscription:** subscription_id, account_id, plan_tier, seats_licensed, seats_active, monthly_price, start_date, end_date, auto_renew

### Structured Data — Product Usage (Mixpanel-like)
- **Tenant:** tenant_id, account_id, setup_date, sso_enabled, scim_enabled, lms_integrated
- **Campaign:** campaign_id, tenant_id, type (phishing/elearning), template_id, launch_date, target_count, status
- **User:** user_id, tenant_id, department, role, registration_date, is_active
- **Campaign Activity:** activity_id, campaign_id, user_id, event_type, timestamp, device
- **Admin Activity:** activity_id, admin_id, tenant_id, action, timestamp, feature_area
- **End User Activity:** activity_id, user_id, event_type, timestamp, module_id

### Unstructured Data
- **Support Tickets:** ticket_id, account_id, category, subject, body, priority, status, created_at, resolved_at
- **Customer Transcripts:** transcript_id, account_id, type (onboarding/review/escalation), date, content
- **Feature Requests:** request_id, account_id, feature_area, description, votes, status
- **Churn Reasons:** reason_id, account_id, churn_date, reason_category, notes
