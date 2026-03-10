"""Structured data generator for SoSafe — cybersecurity awareness platform.

Follows the reference generate_data.py pattern: segment dict, state machine events,
generate_all() orchestration writing to SQLite via db.py.
"""

import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from .db import write_df

fake = Faker()
Faker.seed(42)
np.random.seed(42)
random.seed(42)

NUM_ACCOUNTS = 200
TARGET_EVENTS = 50_000

INDUSTRIES = [
    "Automotive", "Telecom", "Retail", "Finance",
    "Manufacturing", "Government", "Healthcare", "Technology",
]

COUNTRIES = [
    "Germany", "Austria", "Switzerland", "UK",
    "Sweden", "Norway", "Denmark", "Netherlands",
    "France", "USA",
]

# Same shape as reference's SEGMENTS dict — ratio, value ranges, churn, activity frequencies
PLAN_TIERS = {
    "Essential": {
        "ratio": 0.35,
        "arr_range": (5_000, 20_000),
        "churn_rate": 0.25,
        "login_freq": (2, 6),       # admin logins per month
        "campaign_freq": (1, 3),    # campaigns per quarter
        "entitled_features": ["elearning", "basic_phishing"],
    },
    "Professional": {
        "ratio": 0.35,
        "arr_range": (20_000, 80_000),
        "churn_rate": 0.15,
        "login_freq": (4, 10),
        "campaign_freq": (2, 6),
        "entitled_features": [
            "elearning", "basic_phishing", "advanced_phishing", "report_button",
        ],
    },
    "Premium": {
        "ratio": 0.20,
        "arr_range": (80_000, 250_000),
        "churn_rate": 0.08,
        "login_freq": (8, 18),
        "campaign_freq": (4, 12),
        "entitled_features": [
            "elearning", "basic_phishing", "advanced_phishing",
            "report_button", "sofie", "human_risk_os",
        ],
    },
    "Ultimate": {
        "ratio": 0.10,
        "arr_range": (250_000, 800_000),
        "churn_rate": 0.05,
        "login_freq": (10, 22),
        "campaign_freq": (8, 20),
        "entitled_features": [
            "elearning", "basic_phishing", "advanced_phishing",
            "report_button", "sofie", "human_risk_os", "sso", "scim",
        ],
    },
}

FEATURES = [
    {"name": "elearning", "activation_difficulty": "low"},
    {"name": "basic_phishing", "activation_difficulty": "low"},
    {"name": "advanced_phishing", "activation_difficulty": "medium"},
    {"name": "report_button", "activation_difficulty": "high"},
    {"name": "sofie", "activation_difficulty": "high"},
    {"name": "human_risk_os", "activation_difficulty": "medium"},
    {"name": "sso", "activation_difficulty": "high"},
    {"name": "scim", "activation_difficulty": "high"},
]

ACTIVATION_PROB = {"low": 0.85, "medium": 0.55, "high": 0.30}


# ---------------------------------------------------------------------------
# Account generation
# ---------------------------------------------------------------------------

def generate_accounts(n: int = NUM_ACCOUNTS) -> pd.DataFrame:
    """Generate n B2B SaaS accounts with realistic distributions."""
    tiers = list(PLAN_TIERS.keys())
    tier_probs = [PLAN_TIERS[t]["ratio"] for t in tiers]

    records = []
    for i in range(n):
        tier = np.random.choice(tiers, p=tier_probs)
        cfg = PLAN_TIERS[tier]
        arr = int(np.random.uniform(*cfg["arr_range"]))
        employees = int(np.clip(np.random.lognormal(np.log(arr / 10), 0.5), 50, 100_000))
        churned = int(np.random.random() < cfg["churn_rate"])

        contract_start = fake.date_between(start_date="-2y", end_date="-6m")
        if churned:
            earliest_churn = contract_start + timedelta(days=90)
            latest_churn = datetime.now().date()
            if earliest_churn >= latest_churn:
                earliest_churn = contract_start + timedelta(days=30)
            if earliest_churn >= latest_churn:
                churn_date = latest_churn - timedelta(days=1)
            else:
                churn_date = fake.date_between(
                    start_date=earliest_churn,
                    end_date=latest_churn,
                )
        else:
            churn_date = None

        records.append({
            "account_id": f"ACC-{i + 1:04d}",
            "name": fake.company(),
            "industry": random.choice(INDUSTRIES),
            "employee_count": employees,
            "country": random.choice(COUNTRIES),
            "plan_tier": tier,
            "arr": arr,
            "contract_start": str(contract_start),
            "contract_end": str(contract_start + timedelta(days=365)),
            "churned": churned,
            "churn_date": str(churn_date) if churn_date else None,
            "csm_assigned": fake.first_name(),
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Feature activations
# ---------------------------------------------------------------------------

def generate_feature_activations(accounts_df: pd.DataFrame) -> pd.DataFrame:
    """Generate feature activation matrix: account x feature.

    Key pattern from reference: churned accounts have 0.5x activation probability.
    """
    records = []
    for _, acct in accounts_df.iterrows():
        tier_cfg = PLAN_TIERS[acct["plan_tier"]]
        for feat in FEATURES:
            entitled = feat["name"] in tier_cfg["entitled_features"]
            if entitled:
                prob = ACTIVATION_PROB[feat["activation_difficulty"]]
                if acct["churned"]:
                    prob *= 0.5
                activated = int(np.random.random() < prob)
            else:
                activated = 0

            activation_date = None
            if activated:
                start = pd.to_datetime(acct["contract_start"])
                days_offset = int(np.random.exponential(30)) + 1
                activation_date = str((start + timedelta(days=days_offset)).date())

            records.append({
                "account_id": acct["account_id"],
                "feature": feat["name"],
                "entitled": int(entitled),
                "activated": activated,
                "activation_date": activation_date,
            })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

def generate_campaigns(accounts_df: pd.DataFrame) -> pd.DataFrame:
    """Generate phishing simulation and e-learning campaigns per account.

    Frequency scales with tier. Churned accounts have fewer campaigns.
    """
    records = []
    campaign_id = 1

    for _, acct in accounts_df.iterrows():
        tier_cfg = PLAN_TIERS[acct["plan_tier"]]
        freq_lo, freq_hi = tier_cfg["campaign_freq"]
        # Annualize from quarterly frequency
        n_campaigns = np.random.randint(freq_lo, freq_hi + 1) * 4

        if acct["churned"]:
            n_campaigns = max(1, n_campaigns // 2)

        contract_start = pd.to_datetime(acct["contract_start"])
        end = (
            pd.to_datetime(acct["churn_date"])
            if acct["churned"] and acct["churn_date"]
            else pd.Timestamp.now()
        )
        span_days = max(1, (end - contract_start).days)

        for _ in range(n_campaigns):
            campaign_type = random.choice(["phishing_simulation", "elearning"])
            target_count = np.random.randint(
                50, min(acct["employee_count"], 5000) + 1
            ) if acct["employee_count"] > 50 else acct["employee_count"]
            launch_offset = int(np.random.uniform(0, span_days))
            launch_date = contract_start + timedelta(days=launch_offset)

            records.append({
                "campaign_id": f"CMP-{campaign_id:05d}",
                "account_id": acct["account_id"],
                "type": campaign_type,
                "launch_date": str(launch_date.date()),
                "target_count": int(target_count),
                "status": (
                    "completed"
                    if launch_date < pd.Timestamp.now() - timedelta(days=7)
                    else "active"
                ),
            })
            campaign_id += 1

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Event state machines (adapted from reference's generate_session_events)
# ---------------------------------------------------------------------------

def _generate_admin_session(account, event_id, session_ts):
    """State machine: admin login -> dashboard -> optional campaign creation."""
    events = []
    ts = session_ts

    events.append({
        "event_id": event_id,
        "account_id": account["account_id"],
        "event_type": "admin.login",
        "timestamp": str(ts),
        "campaign_id": None,
        "count": None,
    })
    event_id += 1
    ts += timedelta(seconds=random.randint(5, 30))

    events.append({
        "event_id": event_id,
        "account_id": account["account_id"],
        "event_type": "admin.dashboard_viewed",
        "timestamp": str(ts),
        "campaign_id": None,
        "count": None,
    })
    event_id += 1
    ts += timedelta(seconds=random.randint(30, 300))

    # 30% chance of campaign creation in this session
    if random.random() < 0.3:
        events.append({
            "event_id": event_id,
            "account_id": account["account_id"],
            "event_type": "admin.campaign_created",
            "timestamp": str(ts),
            "campaign_id": None,
            "count": None,
        })
        event_id += 1
        ts += timedelta(seconds=random.randint(60, 600))

        if random.random() < 0.7:
            events.append({
                "event_id": event_id,
                "account_id": account["account_id"],
                "event_type": "admin.campaign_launched",
                "timestamp": str(ts),
                "campaign_id": None,
                "count": None,
            })
            event_id += 1

    return events, event_id


def _generate_simulation_events(account, campaign_id, event_id, base_ts, target_count):
    """State machine: phishing simulation lifecycle."""
    events = []
    ts = base_ts

    n_sent = min(target_count, random.randint(50, 500))
    events.append({
        "event_id": event_id,
        "account_id": account["account_id"],
        "event_type": "simulation.email_sent",
        "timestamp": str(ts),
        "campaign_id": campaign_id,
        "count": n_sent,
    })
    event_id += 1
    ts += timedelta(hours=random.randint(1, 24))

    n_opened = int(n_sent * random.uniform(0.4, 0.8))
    events.append({
        "event_id": event_id,
        "account_id": account["account_id"],
        "event_type": "simulation.email_opened",
        "timestamp": str(ts),
        "campaign_id": campaign_id,
        "count": n_opened,
    })
    event_id += 1
    ts += timedelta(hours=random.randint(1, 48))

    n_clicked = int(n_opened * random.uniform(0.05, 0.25))
    events.append({
        "event_id": event_id,
        "account_id": account["account_id"],
        "event_type": "simulation.link_clicked",
        "timestamp": str(ts),
        "campaign_id": campaign_id,
        "count": n_clicked,
    })
    event_id += 1

    if n_clicked > 0 and random.random() < 0.3:
        n_entered = max(1, int(n_clicked * random.uniform(0.1, 0.4)))
        ts += timedelta(minutes=random.randint(1, 30))
        events.append({
            "event_id": event_id,
            "account_id": account["account_id"],
            "event_type": "simulation.data_entered",
            "timestamp": str(ts),
            "campaign_id": campaign_id,
            "count": n_entered,
        })
        event_id += 1

    n_reported = int(n_sent * random.uniform(0.02, 0.15))
    if n_reported > 0:
        ts += timedelta(hours=random.randint(1, 72))
        events.append({
            "event_id": event_id,
            "account_id": account["account_id"],
            "event_type": "simulation.email_reported",
            "timestamp": str(ts),
            "campaign_id": campaign_id,
            "count": n_reported,
        })
        event_id += 1

    return events, event_id


def _generate_elearning_events(account, campaign_id, event_id, base_ts, target_count):
    """State machine: e-learning campaign lifecycle."""
    events = []
    ts = base_ts

    n_assigned = min(target_count, random.randint(50, 500))
    events.append({
        "event_id": event_id,
        "account_id": account["account_id"],
        "event_type": "elearning.module_assigned",
        "timestamp": str(ts),
        "campaign_id": campaign_id,
        "count": n_assigned,
    })
    event_id += 1
    ts += timedelta(days=random.randint(1, 7))

    n_started = int(n_assigned * random.uniform(0.5, 0.9))
    events.append({
        "event_id": event_id,
        "account_id": account["account_id"],
        "event_type": "elearning.module_started",
        "timestamp": str(ts),
        "campaign_id": campaign_id,
        "count": n_started,
    })
    event_id += 1
    ts += timedelta(days=random.randint(3, 14))

    n_completed = int(n_started * random.uniform(0.4, 0.85))
    events.append({
        "event_id": event_id,
        "account_id": account["account_id"],
        "event_type": "elearning.module_completed",
        "timestamp": str(ts),
        "campaign_id": campaign_id,
        "count": n_completed,
    })
    event_id += 1

    return events, event_id


def _generate_feature_events(account, activations_df, event_id):
    """Generate feature activation events for an account."""
    events = []
    acct_activations = activations_df[
        (activations_df["account_id"] == account["account_id"])
        & (activations_df["activated"] == 1)
    ]

    for _, act in acct_activations.iterrows():
        if act["activation_date"]:
            ts = pd.to_datetime(act["activation_date"])
            events.append({
                "event_id": event_id,
                "account_id": account["account_id"],
                "event_type": f"feature.{act['feature']}_activated",
                "timestamp": str(ts),
                "campaign_id": None,
                "count": None,
            })
            event_id += 1

    return events, event_id


# ---------------------------------------------------------------------------
# Main events generator (adapted from reference's generate_events)
# ---------------------------------------------------------------------------

def generate_events(
    accounts_df: pd.DataFrame,
    campaigns_df: pd.DataFrame,
    activations_df: pd.DataFrame,
    target: int = TARGET_EVENTS,
) -> pd.DataFrame:
    """Generate ~target events using state machine pattern.

    Churned accounts: activity drops 30-60 days before churn_date.
    """
    all_events = []
    event_id = 1

    for idx, acct in accounts_df.iterrows():
        contract_start = pd.to_datetime(acct["contract_start"])
        end_date = (
            pd.to_datetime(acct["churn_date"])
            if acct["churned"] and acct["churn_date"]
            else pd.Timestamp.now()
        )
        span_days = max(1, (end_date - contract_start).days)

        tier_cfg = PLAN_TIERS[acct["plan_tier"]]
        login_lo, login_hi = tier_cfg["login_freq"]
        months = max(1, span_days // 30)
        n_sessions = np.random.randint(login_lo, login_hi + 1) * months

        if acct["churned"]:
            n_sessions = max(1, int(n_sessions * 0.6))

        for _ in range(n_sessions):
            day_offset = random.randint(0, span_days - 1)
            session_ts = contract_start + timedelta(
                days=day_offset,
                hours=random.randint(8, 18),
                minutes=random.randint(0, 59),
            )

            # Churned accounts: skip ~60% of sessions in the 30-60 days before churn
            if acct["churned"] and acct["churn_date"]:
                churn_dt = pd.to_datetime(acct["churn_date"])
                days_before_churn = (churn_dt - session_ts).days
                if 0 < days_before_churn < 60 and random.random() < 0.6:
                    continue

            evts, event_id = _generate_admin_session(acct, event_id, session_ts)
            all_events.extend(evts)

        # Campaign events
        acct_campaigns = campaigns_df[campaigns_df["account_id"] == acct["account_id"]]
        for _, cmp in acct_campaigns.iterrows():
            launch_ts = pd.to_datetime(cmp["launch_date"])
            if cmp["type"] == "phishing_simulation":
                evts, event_id = _generate_simulation_events(
                    acct, cmp["campaign_id"], event_id, launch_ts, cmp["target_count"],
                )
            else:
                evts, event_id = _generate_elearning_events(
                    acct, cmp["campaign_id"], event_id, launch_ts, cmp["target_count"],
                )
            all_events.extend(evts)

        # Feature activation events
        evts, event_id = _generate_feature_events(acct, activations_df, event_id)
        all_events.extend(evts)

        if (idx + 1) % 50 == 0:
            print(f"  Processed {idx + 1}/{len(accounts_df)} accounts ({len(all_events)} events)")

    df = pd.DataFrame(all_events)
    print(f"Generated {len(df)} events (target: {target})")
    return df


# ---------------------------------------------------------------------------
# Orchestrator (same pattern as reference's generate_all)
# ---------------------------------------------------------------------------

def generate_all():
    """Generate complete SoSafe dataset and write to sosafe.db."""
    company = "sosafe"

    print("Generating accounts...")
    accounts = generate_accounts()
    write_df(accounts, "accounts", company)

    print("Generating feature activations...")
    activations = generate_feature_activations(accounts)
    write_df(activations, "feature_activations", company)

    print("Generating campaigns...")
    campaigns = generate_campaigns(accounts)
    write_df(campaigns, "campaigns", company)

    print("Generating events...")
    events = generate_events(accounts, campaigns, activations)
    write_df(events, "events", company)

    # Print summary (same pattern as reference)
    print("\n=== SoSafe Data Summary ===")
    for tier in PLAN_TIERS:
        tier_accts = accounts[accounts["plan_tier"] == tier]
        print(
            f"  {tier}: {len(tier_accts)} accounts, "
            f"avg ARR ${tier_accts['arr'].mean():,.0f}, "
            f"churn rate {tier_accts['churned'].mean():.0%}"
        )

    print(f"\nTotal accounts: {len(accounts)}")
    print(
        f"Total feature activations: {len(activations)} "
        f"({activations['activated'].sum()} activated)"
    )
    print(f"Total campaigns: {len(campaigns)}")
    print(f"Total events: {len(events)}")

    return {"accounts": accounts, "activations": activations, "campaigns": campaigns, "events": events}


if __name__ == "__main__":
    generate_all()
