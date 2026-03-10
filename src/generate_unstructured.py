"""Claude-powered unstructured text generation for B2B SaaS.

Generates support tickets, customer transcripts, reviews, churn reasons,
and feature requests conditioned on account context from the structured data in SQLite.

Uses asyncio with 10 concurrent workers for ~6x speedup over serial.
"""

import asyncio
import json
import random
import sys

import anthropic
import pandas as pd
from tqdm.asyncio import tqdm as atqdm

from .db import read_df, write_df

MAX_WORKERS = 10

COMPANY_CONFIG = {
    "sosafe": {
        "ticket_categories": [
            "Integration Setup", "Campaign Configuration", "User Provisioning",
            "Report Button Installation", "SSO/SCIM Setup", "Dashboard/Analytics",
            "Billing/Licensing", "Feature Request", "Bug Report", "Training Content",
        ],
        "feature_request_categories": [
            "Reporting & Analytics", "Integration", "Compliance",
            "User Experience", "Campaign Management", "Content Library",
            "Automation", "API & Extensibility", "Mobile", "Localization",
        ],
        "system_prompt": (
            "You are a synthetic data generator for a B2B SaaS cybersecurity awareness platform "
            "(similar to SoSafe). Generate realistic business data that reflects real-world patterns. "
            "Return ONLY valid JSON with no markdown fencing or commentary."
        ),
        "domain_description": "cybersecurity awareness platform",
    },
    "synthflow": {
        "ticket_categories": [
            "Agent Configuration", "Call Quality", "CRM Integration",
            "Telephony Setup", "Voice Cloning", "API/Webhooks",
            "Billing/Usage", "Feature Request", "Bug Report", "Latency/Performance",
        ],
        "feature_request_categories": [
            "Voice Quality", "Integration", "Analytics & Reporting",
            "Call Management", "Agent Builder", "API & Webhooks",
            "Multi-language", "Compliance", "Automation", "User Experience",
        ],
        "system_prompt": (
            "You are a synthetic data generator for a B2B SaaS AI voice agent platform "
            "(similar to SynthFlow). Generate realistic business data that reflects real-world patterns. "
            "Return ONLY valid JSON with no markdown fencing or commentary."
        ),
        "domain_description": "AI voice agent platform",
    },
}

TICKET_CATEGORIES = [
    "Integration Setup",
    "Campaign Configuration",
    "User Provisioning",
    "Report Button Installation",
    "SSO/SCIM Setup",
    "Dashboard/Analytics",
    "Billing/Licensing",
    "Feature Request",
    "Bug Report",
    "Training Content",
]

SYSTEM_PROMPT = (
    "You are a synthetic data generator for a B2B SaaS cybersecurity awareness platform "
    "(similar to SoSafe). Generate realistic business data that reflects real-world patterns. "
    "Return ONLY valid JSON with no markdown fencing or commentary."
)


async def _call_claude(
    client: anthropic.AsyncAnthropic,
    prompt: str,
    semaphore: asyncio.Semaphore,
    system: str = SYSTEM_PROMPT,
    max_tokens: int = 4096,
) -> str:
    """Call Claude API with concurrency limit and retry with backoff."""
    async with semaphore:
        for attempt in range(3):
            try:
                response = await client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            except anthropic.RateLimitError:
                wait = 2 ** attempt * 3
                await asyncio.sleep(wait)
            except anthropic.APIError as e:
                if attempt < 2:
                    wait = 2 ** attempt * 2
                    await asyncio.sleep(wait)
                else:
                    raise
    raise RuntimeError("Failed after 3 retries")


def _parse_json_response(response: str) -> list | dict:
    """Extract JSON from Claude's response, handling markdown fencing."""
    text = response.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts[1:]:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue
    return json.loads(text)


def _build_account_context(acct, activations_df) -> dict:
    """Build context dict for a single account."""
    acct_acts = activations_df[activations_df["account_id"] == acct["account_id"]]
    activated = acct_acts[acct_acts["activated"] == 1]["feature"].tolist()
    not_activated = acct_acts[
        (acct_acts["entitled"] == 1) & (acct_acts["activated"] == 0)
    ]["feature"].tolist()

    return {
        "account_id": acct["account_id"],
        "name": acct["name"],
        "plan_tier": acct["plan_tier"],
        "industry": acct["industry"],
        "employees": int(acct["employee_count"]),
        "arr": int(acct["arr"]),
        "churned": bool(acct["churned"]),
        "activated_features": activated,
        "unactivated_features": not_activated,
    }


# ---------------------------------------------------------------------------
# Support tickets (batch 10 per Claude call, 10 concurrent)
# ---------------------------------------------------------------------------

async def generate_support_tickets(company: str, n: int = 500) -> pd.DataFrame:
    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(MAX_WORKERS)
    config = COMPANY_CONFIG.get(company, COMPANY_CONFIG["sosafe"])
    accounts = read_df("accounts", company)
    activations = read_df("feature_activations", company)

    batch_size = 10
    n_batches = n // batch_size

    async def _one_batch(batch_idx):
        sample_accts = accounts.sample(batch_size, replace=True)
        acct_contexts = [
            _build_account_context(row, activations)
            for _, row in sample_accts.iterrows()
        ]
        prompt = f"""Generate exactly {batch_size} realistic B2B SaaS support tickets for a {config["domain_description"]}.

Account contexts (one ticket per account):
{json.dumps(acct_contexts, indent=2)}

Guidelines:
- Churned accounts should have frustrated or unresolved tickets
- Accounts with unactivated features should ask about setup difficulties
- Higher-tier accounts may have more complex integration issues
- Mix priorities: 50% medium, 25% high, 15% low, 10% critical

Categories to use: {json.dumps(config["ticket_categories"])}

Return a JSON array with {batch_size} objects:
{{"account_id": "ACC-XXXX", "category": "...", "subject": "one-line summary", "body": "2-4 sentences, realistic support language", "priority": "low|medium|high|critical", "status": "open|in_progress|resolved|closed", "created_at": "YYYY-MM-DD", "resolved_at": "YYYY-MM-DD or null"}}"""

        try:
            response = await _call_claude(client, prompt, sem, system=config["system_prompt"])
            batch_tickets = _parse_json_response(response)
            if isinstance(batch_tickets, list):
                for i, t in enumerate(batch_tickets):
                    t["ticket_id"] = f"TKT-{batch_idx * batch_size + i + 1:05d}"
                return batch_tickets
        except (json.JSONDecodeError, RuntimeError) as e:
            print(f"  Warning: Failed batch {batch_idx}: {e}")
        return []

    tasks = [_one_batch(i) for i in range(n_batches)]
    results = []
    for coro in atqdm(asyncio.as_completed(tasks), total=n_batches, desc="Tickets"):
        results.extend(await coro)

    df = pd.DataFrame(results)
    write_df(df, "support_tickets", company)
    print(f"Generated {len(df)} support tickets")
    return df


# ---------------------------------------------------------------------------
# Transcripts (one per call, 10 concurrent)
# ---------------------------------------------------------------------------

async def generate_transcripts(company: str, n: int = 50) -> pd.DataFrame:
    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(MAX_WORKERS)
    config = COMPANY_CONFIG.get(company, COMPANY_CONFIG["sosafe"])
    accounts = read_df("accounts", company)
    activations = read_df("feature_activations", company)
    churned_accts = accounts[accounts["churned"] == 1]

    type_counts = {
        "onboarding": int(n * 0.40),
        "qbr": int(n * 0.25),
        "escalation": int(n * 0.20),
        "churn_exit": n - int(n * 0.40) - int(n * 0.25) - int(n * 0.20),
    }

    # Build all prompts upfront
    jobs = []
    transcript_id = 1
    for ttype, count in type_counts.items():
        source = churned_accts if ttype == "churn_exit" and len(churned_accts) > 0 else accounts
        for _ in range(count):
            acct = source.sample(1).iloc[0]
            ctx = _build_account_context(acct, activations)
            guidance = {
                "churn_exit": "This is a churn exit interview. The customer is leaving. Explore why.",
                "qbr": "This is a quarterly business review. Discuss usage metrics, feature adoption, ROI.",
                "escalation": "This is an escalation call. The customer has an urgent issue.",
                "onboarding": "This is an onboarding call. Walk through initial setup and feature activation.",
            }[ttype]
            prompt = f"""Generate a realistic {ttype.replace('_', ' ')} call transcript for a B2B {config["domain_description"]}.

Account context:
{json.dumps(ctx, indent=2)}

Transcript type: {ttype}
- {guidance}

Format as a realistic dialogue between CSM (Customer Success Manager) and the customer contact.
Include 8-15 exchanges. Reference specific features and metrics from the context.

Return a JSON object:
{{"account_id": "{ctx['account_id']}", "type": "{ttype}", "date": "YYYY-MM-DD", "content": "the full transcript text", "summary": "2-3 sentence summary of key points"}}"""
            jobs.append((transcript_id, prompt))
            transcript_id += 1

    async def _one_transcript(tid, prompt):
        try:
            response = await _call_claude(client, prompt, sem, system=config["system_prompt"], max_tokens=2048)
            transcript = _parse_json_response(response)
            transcript["transcript_id"] = f"TRN-{tid:04d}"
            return transcript
        except (json.JSONDecodeError, RuntimeError) as e:
            print(f"  Warning: Failed transcript {tid}: {e}")
            return None

    tasks = [_one_transcript(tid, p) for tid, p in jobs]
    transcripts = []
    for coro in atqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Transcripts"):
        result = await coro
        if result:
            transcripts.append(result)

    df = pd.DataFrame(transcripts)
    write_df(df, "transcripts", company)
    print(f"Generated {len(df)} transcripts")
    return df


# ---------------------------------------------------------------------------
# Reviews (batch 10 per call, 10 concurrent)
# ---------------------------------------------------------------------------

async def generate_reviews(company: str, n: int = 100) -> pd.DataFrame:
    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(MAX_WORKERS)
    config = COMPANY_CONFIG.get(company, COMPANY_CONFIG["sosafe"])
    accounts = read_df("accounts", company)
    activations = read_df("feature_activations", company)

    batch_size = 10
    n_batches = n // batch_size

    async def _one_batch(batch_idx):
        sample_accts = accounts.sample(batch_size, replace=True)
        acct_contexts = [
            _build_account_context(row, activations)
            for _, row in sample_accts.iterrows()
        ]
        prompt = f"""Generate {batch_size} realistic G2/NPS-style reviews for a {config["domain_description"]}.

Account contexts:
{json.dumps(acct_contexts, indent=2)}

Sentiment distribution for this batch:
- 3 positive (rating 8-10, highlight value and ease of use)
- 5 neutral (rating 5-7, mixed feedback, feature requests)
- 2 negative (rating 1-4, frustrations, unmet expectations)

Churned accounts should have more negative reviews. Higher-tier accounts with many unactivated features should mention setup difficulty.

Return a JSON array:
{{"account_id": "ACC-XXXX", "rating": 1-10, "title": "short title", "body": "3-5 sentences review text", "sentiment": "positive|neutral|negative", "date": "YYYY-MM-DD"}}"""

        try:
            response = await _call_claude(client, prompt, sem, system=config["system_prompt"])
            batch_reviews = _parse_json_response(response)
            if isinstance(batch_reviews, list):
                for i, r in enumerate(batch_reviews):
                    r["review_id"] = f"REV-{batch_idx * batch_size + i + 1:04d}"
                return batch_reviews
        except (json.JSONDecodeError, RuntimeError) as e:
            print(f"  Warning: Failed batch {batch_idx}: {e}")
        return []

    tasks = [_one_batch(i) for i in range(n_batches)]
    results = []
    for coro in atqdm(asyncio.as_completed(tasks), total=n_batches, desc="Reviews"):
        results.extend(await coro)

    df = pd.DataFrame(results)
    write_df(df, "reviews", company)
    print(f"Generated {len(df)} reviews")
    return df


# ---------------------------------------------------------------------------
# Churn reasons (batch 10, 10 concurrent)
# ---------------------------------------------------------------------------

async def generate_churn_reasons(company: str) -> pd.DataFrame:
    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(MAX_WORKERS)
    config = COMPANY_CONFIG.get(company, COMPANY_CONFIG["sosafe"])
    accounts = read_df("accounts", company)
    activations = read_df("feature_activations", company)

    churned = accounts[accounts["churned"] == 1]
    if len(churned) == 0:
        print("No churned accounts found")
        return pd.DataFrame()

    batch_size = 10

    async def _one_batch(batch_start):
        batch = churned.iloc[batch_start:batch_start + batch_size]
        acct_contexts = [
            _build_account_context(row, activations)
            for _, row in batch.iterrows()
        ]
        prompt = f"""For each of these churned B2B SaaS accounts, generate a realistic churn reason tied to their actual data signals.

Account contexts:
{json.dumps(acct_contexts, indent=2)}

Churn reason categories: "poor_adoption", "budget_cuts", "competitor_switch", "missing_features", "poor_support", "champion_left", "low_roi"

The churn reason should correlate with the account data:
- Many unactivated features -> "poor_adoption" or "low_roi"
- Small company / low ARR -> "budget_cuts"
- High-tier with few activated features -> "missing_features" or "poor_support"

Return a JSON array:
{{"account_id": "ACC-XXXX", "churn_date": "YYYY-MM-DD", "reason_category": "...", "notes": "2-3 sentences explaining specific reasons, referencing features and metrics"}}"""

        try:
            response = await _call_claude(client, prompt, sem, system=config["system_prompt"])
            batch_reasons = _parse_json_response(response)
            if isinstance(batch_reasons, list):
                for i, r in enumerate(batch_reasons):
                    r["reason_id"] = f"CHR-{batch_start + i + 1:04d}"
                return batch_reasons
        except (json.JSONDecodeError, RuntimeError) as e:
            print(f"  Warning: Failed batch at {batch_start}: {e}")
        return []

    starts = list(range(0, len(churned), batch_size))
    tasks = [_one_batch(s) for s in starts]
    results = []
    for coro in atqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Churn reasons"):
        results.extend(await coro)

    df = pd.DataFrame(results)
    write_df(df, "churn_reasons", company)
    print(f"Generated {len(df)} churn reasons")
    return df


# ---------------------------------------------------------------------------
# Feature requests (batch 10, 10 concurrent) — Step 5
# ---------------------------------------------------------------------------

async def generate_feature_requests(company: str, n: int = 250) -> pd.DataFrame:
    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(MAX_WORKERS)
    config = COMPANY_CONFIG.get(company, COMPANY_CONFIG["sosafe"])
    accounts = read_df("accounts", company)
    activations = read_df("feature_activations", company)

    # Load users table to pick submitters
    try:
        users = read_df("users", company)
    except Exception:
        users = pd.DataFrame()

    rng = random.Random(44_001)
    batch_size = 10
    n_batches = n // batch_size

    async def _one_batch(batch_idx):
        sample_accts = accounts.sample(batch_size, replace=True, random_state=rng.randint(0, 100_000))
        acct_contexts = []
        user_ids = []
        for _, row in sample_accts.iterrows():
            ctx = _build_account_context(row, activations)
            # Pick a random admin/manager user if users table exists
            submitter_id = None
            if len(users) > 0:
                admin_mgr = users[
                    (users["account_id"] == row["account_id"])
                    & (users["role"].isin(["admin", "manager"]))
                ]
                if len(admin_mgr) > 0:
                    submitter_id = admin_mgr.sample(1, random_state=rng.randint(0, 100_000)).iloc[0]["user_id"]
            ctx["submitter_user_id"] = submitter_id
            acct_contexts.append(ctx)
            user_ids.append(submitter_id)

        categories = json.dumps(config.get("feature_request_categories", []))
        prompt = f"""Generate exactly {batch_size} realistic ProductBoard-style feature requests for a {config["domain_description"]}.

Account contexts (one request per account):
{json.dumps(acct_contexts, indent=2)}

Guidelines:
- Accounts with many unactivated features should request improvements to those features
- Higher-tier accounts request advanced integrations and enterprise features
- Churned accounts may have submitted requests that went unaddressed
- Status distribution: 40% under_review, 25% planned, 20% in_progress, 10% completed, 5% declined
- Priority distribution: 20% critical, 30% high, 35% medium, 15% low
- Votes should correlate with how broadly applicable the feature is (1-50)

Categories to use: {categories}

Return a JSON array with {batch_size} objects:
{{"account_id": "ACC-XXXX", "user_id": "USR-XXXXX or null", "title": "short feature title", "description": "2-4 sentences describing the feature request with business context", "category": "...", "priority": "critical|high|medium|low", "status": "under_review|planned|in_progress|completed|declined", "votes": 1-50, "submitted_at": "YYYY-MM-DD", "updated_at": "YYYY-MM-DD"}}"""

        try:
            response = await _call_claude(client, prompt, sem, system=config["system_prompt"])
            batch_requests = _parse_json_response(response)
            if isinstance(batch_requests, list):
                for i, fr in enumerate(batch_requests):
                    fr["request_id"] = f"FR-{batch_idx * batch_size + i + 1:04d}"
                    # Ensure user_id is set from our known users
                    if i < len(user_ids) and user_ids[i]:
                        fr["user_id"] = user_ids[i]
                return batch_requests
        except (json.JSONDecodeError, RuntimeError) as e:
            print(f"  Warning: Failed batch {batch_idx}: {e}")
        return []

    tasks = [_one_batch(i) for i in range(n_batches)]
    results = []
    for coro in atqdm(asyncio.as_completed(tasks), total=n_batches, desc="Feature requests"):
        results.extend(await coro)

    df = pd.DataFrame(results)
    write_df(df, "feature_requests", company)
    print(f"Generated {len(df)} feature requests")
    return df


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def generate_all(company: str):
    """Generate all unstructured data for a company with parallel workers."""
    print(f"\n=== Generating unstructured data for {company} (max {MAX_WORKERS} workers) ===\n")

    print("1/5 Support tickets (500)...")
    await generate_support_tickets(company, 500)

    print("\n2/5 Transcripts (50)...")
    await generate_transcripts(company, 50)

    print("\n3/5 Reviews (100)...")
    await generate_reviews(company, 100)

    print("\n4/5 Churn reasons...")
    await generate_churn_reasons(company)

    print("\n5/5 Feature requests (250)...")
    await generate_feature_requests(company, 250)

    print(f"\nUnstructured data generation complete for {company}")


if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "sosafe"
    asyncio.run(generate_all(company))
