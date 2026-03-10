"""Structured data generator for SoSafe — cybersecurity awareness platform.

Follows the reference generate_data.py pattern: segment dict, state machine events,
generate_all() orchestration writing to SQLite via db.py.
"""

import json
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
        "user_range": (5, 20),
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
        "user_range": (15, 50),
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
        "user_range": (30, 80),
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
        "user_range": (50, 150),
    },
}

TIER_ORDER = list(PLAN_TIERS.keys())

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

DEPARTMENTS = [
    "Security", "IT", "HR", "Operations",
    "Finance", "Marketing", "Sales", "Engineering",
]
DEPARTMENT_WEIGHTS = [0.20, 0.20, 0.15, 0.12, 0.10, 0.08, 0.08, 0.07]


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
# Subscriptions (Step 1)
# ---------------------------------------------------------------------------

def generate_subscriptions(accounts_df: pd.DataFrame) -> pd.DataFrame:
    """Generate subscription history per account — plan changes over time."""
    rng = random.Random(42_001)
    records = []
    sub_id = 1

    for _, acct in accounts_df.iterrows():
        tier = acct["plan_tier"]
        arr = acct["arr"]
        cfg = PLAN_TIERS[tier]
        contract_start = pd.to_datetime(acct["contract_start"]).date()
        employees = acct["employee_count"]
        seats = int(employees * rng.uniform(0.3, 0.8))
        modules = json.dumps(cfg["entitled_features"])

        # Initial subscription
        start = contract_start
        end = start + timedelta(days=365)
        current_tier = tier
        current_arr = arr
        records.append({
            "subscription_id": f"SUB-{sub_id:04d}",
            "account_id": acct["account_id"],
            "plan_tier": current_tier,
            "mrr": round(current_arr / 12, 2),
            "arr": current_arr,
            "start_date": str(start),
            "end_date": str(end),
            "change_type": "initial",
            "seats": seats,
            "modules": modules,
        })
        sub_id += 1

        # 0-3 additional events
        n_changes = rng.randint(0, 3)
        for _ in range(n_changes):
            start = end
            roll = rng.random()
            tier_idx = TIER_ORDER.index(current_tier)

            if roll < 0.70:
                # Renewal — same tier, ARR +/- 5%
                current_arr = int(current_arr * rng.uniform(0.95, 1.05))
                change_type = "renewal"
            elif roll < 0.90:
                # Upgrade
                if tier_idx < len(TIER_ORDER) - 1:
                    current_tier = TIER_ORDER[tier_idx + 1]
                    new_cfg = PLAN_TIERS[current_tier]
                    current_arr = int(rng.uniform(*new_cfg["arr_range"]))
                    modules = json.dumps(new_cfg["entitled_features"])
                    change_type = "upgrade"
                else:
                    current_arr = int(current_arr * rng.uniform(0.95, 1.05))
                    change_type = "renewal"
            else:
                # Downgrade
                if tier_idx > 0:
                    current_tier = TIER_ORDER[tier_idx - 1]
                    new_cfg = PLAN_TIERS[current_tier]
                    current_arr = int(rng.uniform(*new_cfg["arr_range"]))
                    modules = json.dumps(new_cfg["entitled_features"])
                    change_type = "downgrade"
                else:
                    current_arr = int(current_arr * rng.uniform(0.95, 1.05))
                    change_type = "renewal"

            end = start + timedelta(days=365)
            records.append({
                "subscription_id": f"SUB-{sub_id:04d}",
                "account_id": acct["account_id"],
                "plan_tier": current_tier,
                "mrr": round(current_arr / 12, 2),
                "arr": current_arr,
                "start_date": str(start),
                "end_date": str(end),
                "change_type": change_type,
                "seats": seats,
                "modules": modules,
            })
            sub_id += 1

        # Churned accounts get a final "churned" event
        if acct["churned"] and acct["churn_date"]:
            churn_date = pd.to_datetime(acct["churn_date"]).date()
            records.append({
                "subscription_id": f"SUB-{sub_id:04d}",
                "account_id": acct["account_id"],
                "plan_tier": current_tier,
                "mrr": 0,
                "arr": 0,
                "start_date": str(churn_date),
                "end_date": str(churn_date),
                "change_type": "churned",
                "seats": 0,
                "modules": "[]",
            })
            sub_id += 1

    df = pd.DataFrame(records)
    print(f"Generated {len(df)} subscriptions")
    return df


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
# Tenants (Step 2)
# ---------------------------------------------------------------------------

def generate_tenants(accounts_df: pd.DataFrame, activations_df: pd.DataFrame) -> pd.DataFrame:
    """Generate tenant/workspace rows — 1:1 with accounts."""
    rng = random.Random(42_002)
    records = []

    for i, (_, acct) in enumerate(accounts_df.iterrows()):
        acct_acts = activations_df[
            (activations_df["account_id"] == acct["account_id"])
            & (activations_df["activated"] == 1)
        ]
        activated_set = set(acct_acts["feature"].tolist())

        # Slugify name for domain
        slug = acct["name"].lower().replace(" ", "-").replace(",", "").replace(".", "")
        slug = slug[:30]
        domain = f"{slug}.sosafe.io"

        user_limit = int(acct["employee_count"] * rng.uniform(0.5, 1.2))
        if acct["churned"]:
            active_users = int(user_limit * rng.uniform(0.05, 0.3))
        else:
            active_users = int(user_limit * rng.uniform(0.3, 0.9))

        tier = acct["plan_tier"]
        if tier in ("Premium", "Ultimate"):
            setup = rng.uniform(0.7, 1.0)
        else:
            setup = rng.uniform(0.4, 0.8)
        if acct["churned"]:
            setup *= 0.6
        setup = round(min(setup, 1.0), 2)

        env_roll = rng.random()
        if env_roll < 0.85:
            environment = "production"
        elif env_roll < 0.95:
            environment = "staging"
        else:
            environment = "sandbox"

        records.append({
            "tenant_id": f"TNT-{i + 1:04d}",
            "account_id": acct["account_id"],
            "domain": domain,
            "created_at": acct["contract_start"],
            "sso_enabled": int("sso" in activated_set),
            "scim_enabled": int("scim" in activated_set),
            "report_button_deployed": int("report_button" in activated_set),
            "sofie_enabled": int("sofie" in activated_set),
            "user_limit": user_limit,
            "active_users": active_users,
            "setup_completion": setup,
            "environment": environment,
        })

    df = pd.DataFrame(records)
    print(f"Generated {len(df)} tenants")
    return df


# ---------------------------------------------------------------------------
# Users (Step 3)
# ---------------------------------------------------------------------------

def generate_users(accounts_df: pd.DataFrame, tenants_df: pd.DataFrame) -> pd.DataFrame:
    """Generate individual users per account."""
    rng = random.Random(42_003)
    user_fake = Faker()
    Faker.seed(42_003)
    records = []
    user_id = 1

    tenant_map = dict(zip(tenants_df["account_id"], tenants_df["tenant_id"]))
    domain_map = {}
    for _, t in tenants_df.iterrows():
        # Strip .sosafe.io suffix for email domain
        d = t["domain"]
        if d.endswith(".sosafe.io"):
            d = d[: -len(".sosafe.io")]
        domain_map[t["account_id"]] = d + ".com"

    for _, acct in accounts_df.iterrows():
        tier_cfg = PLAN_TIERS[acct["plan_tier"]]
        lo, hi = tier_cfg["user_range"]
        n_users = rng.randint(lo, hi)

        contract_start = pd.to_datetime(acct["contract_start"])
        tenant_id = tenant_map.get(acct["account_id"], "")
        email_domain = domain_map.get(acct["account_id"], "example.com")

        for j in range(n_users):
            # Role distribution: first user always admin, then 5% admin, 15% manager, 80% end_user
            if j == 0:
                role = "admin"
            else:
                r = rng.random()
                if r < 0.05:
                    role = "admin"
                elif r < 0.20:
                    role = "manager"
                else:
                    role = "end_user"

            dept = rng.choices(DEPARTMENTS, weights=DEPARTMENT_WEIGHTS, k=1)[0]

            # created_at: admins day 0-7, others 0-90
            if role == "admin":
                day_offset = rng.randint(0, 7)
            else:
                day_offset = rng.randint(0, 90)
            created_at = contract_start + timedelta(days=day_offset)

            # last_active
            now = pd.Timestamp.now()
            if acct["churned"] and acct["churn_date"]:
                churn_dt = pd.to_datetime(acct["churn_date"])
                last_active = churn_dt - timedelta(days=rng.randint(0, 60))
            else:
                if role == "end_user" and rng.random() < 0.10:
                    # 10% inactive end users
                    last_active = now - timedelta(days=rng.randint(91, 365))
                else:
                    last_active = now - timedelta(days=rng.randint(0, 30))

            # status
            if acct["churned"]:
                s = rng.random()
                if s < 0.30:
                    status = "active"
                elif s < 0.70:
                    status = "inactive"
                else:
                    status = "deprovisioned"
            else:
                s = rng.random()
                if s < 0.85:
                    status = "active"
                elif s < 0.95:
                    status = "inactive"
                else:
                    status = "deprovisioned"

            first = user_fake.first_name()
            last = user_fake.last_name()
            name = f"{first} {last}"
            email = f"{first.lower()}.{last.lower()}@{email_domain}"

            records.append({
                "user_id": f"USR-{user_id:05d}",
                "account_id": acct["account_id"],
                "tenant_id": tenant_id,
                "name": name,
                "email": email,
                "role": role,
                "department": dept,
                "created_at": str(created_at.date()),
                "last_active": str(last_active.date()),
                "status": status,
            })
            user_id += 1

    df = pd.DataFrame(records)
    print(f"Generated {len(df)} users")
    return df


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
# Event state machines (Step 4 — refactored to per-user rows)
# ---------------------------------------------------------------------------

def _get_account_users(users_df, account_id, role=None):
    """Get users for an account, optionally filtered by role."""
    mask = users_df["account_id"] == account_id
    if role:
        mask = mask & (users_df["role"] == role)
    return users_df[mask]


def _generate_admin_session(account, event_id, session_ts, user_id=None):
    """State machine: admin login -> dashboard -> optional campaign creation."""
    events = []
    ts = session_ts

    events.append({
        "event_id": event_id,
        "account_id": account["account_id"],
        "user_id": user_id,
        "event_type": "admin.login",
        "timestamp": str(ts),
        "campaign_id": None,
    })
    event_id += 1
    ts += timedelta(seconds=random.randint(5, 30))

    events.append({
        "event_id": event_id,
        "account_id": account["account_id"],
        "user_id": user_id,
        "event_type": "admin.dashboard_viewed",
        "timestamp": str(ts),
        "campaign_id": None,
    })
    event_id += 1
    ts += timedelta(seconds=random.randint(30, 300))

    # 30% chance of campaign creation in this session
    if random.random() < 0.3:
        events.append({
            "event_id": event_id,
            "account_id": account["account_id"],
            "user_id": user_id,
            "event_type": "admin.campaign_created",
            "timestamp": str(ts),
            "campaign_id": None,
        })
        event_id += 1
        ts += timedelta(seconds=random.randint(60, 600))

        if random.random() < 0.7:
            events.append({
                "event_id": event_id,
                "account_id": account["account_id"],
                "user_id": user_id,
                "event_type": "admin.campaign_launched",
                "timestamp": str(ts),
                "campaign_id": None,
            })
            event_id += 1

    return events, event_id


def _generate_simulation_events(account, campaign_id, event_id, base_ts, target_count,
                                user_pool, user_rng):
    """State machine: phishing simulation per-user funnel."""
    events = []
    ts = base_ts

    n_target = min(target_count, len(user_pool)) if len(user_pool) > 0 else 0
    if n_target == 0:
        return events, event_id

    targeted_users = user_rng.sample(list(user_pool["user_id"]), k=min(n_target, len(user_pool)))

    for uid in targeted_users:
        user_ts = ts + timedelta(seconds=user_rng.randint(0, 3600))
        # email_sent
        events.append({
            "event_id": event_id,
            "account_id": account["account_id"],
            "user_id": uid,
            "event_type": "simulation.email_sent",
            "timestamp": str(user_ts),
            "campaign_id": campaign_id,
        })
        event_id += 1

        # email_opened (40-80%)
        if user_rng.random() < user_rng.uniform(0.4, 0.8):
            user_ts += timedelta(minutes=user_rng.randint(5, 1440))
            events.append({
                "event_id": event_id,
                "account_id": account["account_id"],
                "user_id": uid,
                "event_type": "simulation.email_opened",
                "timestamp": str(user_ts),
                "campaign_id": campaign_id,
            })
            event_id += 1

            # link_clicked (5-25%)
            if user_rng.random() < user_rng.uniform(0.05, 0.25):
                user_ts += timedelta(minutes=user_rng.randint(1, 60))
                events.append({
                    "event_id": event_id,
                    "account_id": account["account_id"],
                    "user_id": uid,
                    "event_type": "simulation.link_clicked",
                    "timestamp": str(user_ts),
                    "campaign_id": campaign_id,
                })
                event_id += 1

                # data_entered (10-40%)
                if user_rng.random() < user_rng.uniform(0.1, 0.4):
                    user_ts += timedelta(minutes=user_rng.randint(1, 15))
                    events.append({
                        "event_id": event_id,
                        "account_id": account["account_id"],
                        "user_id": uid,
                        "event_type": "simulation.data_entered",
                        "timestamp": str(user_ts),
                        "campaign_id": campaign_id,
                    })
                    event_id += 1

            # email_reported (2-15% of all sent, independent of click)
            if user_rng.random() < user_rng.uniform(0.02, 0.15):
                user_ts += timedelta(minutes=user_rng.randint(10, 4320))
                events.append({
                    "event_id": event_id,
                    "account_id": account["account_id"],
                    "user_id": uid,
                    "event_type": "simulation.email_reported",
                    "timestamp": str(user_ts),
                    "campaign_id": campaign_id,
                })
                event_id += 1

    return events, event_id


def _generate_elearning_events(account, campaign_id, event_id, base_ts, target_count,
                               user_pool, user_rng):
    """State machine: e-learning campaign per-user funnel."""
    events = []
    ts = base_ts

    n_target = min(target_count, len(user_pool)) if len(user_pool) > 0 else 0
    if n_target == 0:
        return events, event_id

    targeted_users = user_rng.sample(list(user_pool["user_id"]), k=min(n_target, len(user_pool)))

    for uid in targeted_users:
        user_ts = ts + timedelta(hours=user_rng.randint(0, 24))
        # module_assigned
        events.append({
            "event_id": event_id,
            "account_id": account["account_id"],
            "user_id": uid,
            "event_type": "elearning.module_assigned",
            "timestamp": str(user_ts),
            "campaign_id": campaign_id,
        })
        event_id += 1

        # module_started (50-90%)
        if user_rng.random() < user_rng.uniform(0.5, 0.9):
            user_ts += timedelta(days=user_rng.randint(1, 7))
            events.append({
                "event_id": event_id,
                "account_id": account["account_id"],
                "user_id": uid,
                "event_type": "elearning.module_started",
                "timestamp": str(user_ts),
                "campaign_id": campaign_id,
            })
            event_id += 1

            # module_completed (40-85%)
            if user_rng.random() < user_rng.uniform(0.4, 0.85):
                user_ts += timedelta(days=user_rng.randint(1, 14))
                events.append({
                    "event_id": event_id,
                    "account_id": account["account_id"],
                    "user_id": uid,
                    "event_type": "elearning.module_completed",
                    "timestamp": str(user_ts),
                    "campaign_id": campaign_id,
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
                "user_id": None,
                "event_type": f"feature.{act['feature']}_activated",
                "timestamp": str(ts),
                "campaign_id": None,
            })
            event_id += 1

    return events, event_id


# ---------------------------------------------------------------------------
# Main events generator (Step 4 — now per-user)
# ---------------------------------------------------------------------------

def generate_events(
    accounts_df: pd.DataFrame,
    campaigns_df: pd.DataFrame,
    activations_df: pd.DataFrame,
    users_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate per-user events using state machine pattern."""
    all_events = []
    event_id = 1
    user_rng = random.Random(42_004)

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

        # Get admin/manager users for this account
        admin_users = _get_account_users(users_df, acct["account_id"], "admin")
        manager_users = _get_account_users(users_df, acct["account_id"], "manager")
        admin_manager_pool = pd.concat([admin_users, manager_users])
        end_users = _get_account_users(users_df, acct["account_id"], "end_user")
        all_acct_users = _get_account_users(users_df, acct["account_id"])

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

            # Pick a random admin/manager for this session
            session_user_id = None
            if len(admin_manager_pool) > 0:
                session_user_id = user_rng.choice(list(admin_manager_pool["user_id"]))

            evts, event_id = _generate_admin_session(acct, event_id, session_ts, user_id=session_user_id)
            all_events.extend(evts)

        # Campaign events — use end_user pool
        acct_campaigns = campaigns_df[campaigns_df["account_id"] == acct["account_id"]]
        for _, cmp in acct_campaigns.iterrows():
            launch_ts = pd.to_datetime(cmp["launch_date"])
            user_pool = end_users if len(end_users) > 0 else all_acct_users
            if cmp["type"] == "phishing_simulation":
                evts, event_id = _generate_simulation_events(
                    acct, cmp["campaign_id"], event_id, launch_ts, cmp["target_count"],
                    user_pool, user_rng,
                )
            else:
                evts, event_id = _generate_elearning_events(
                    acct, cmp["campaign_id"], event_id, launch_ts, cmp["target_count"],
                    user_pool, user_rng,
                )
            all_events.extend(evts)

        # Feature activation events
        evts, event_id = _generate_feature_events(acct, activations_df, event_id)
        all_events.extend(evts)

        if (idx + 1) % 50 == 0:
            print(f"  Processed {idx + 1}/{len(accounts_df)} accounts ({len(all_events):,} events)")

    df = pd.DataFrame(all_events)
    print(f"Generated {len(df):,} events")
    return df


# ---------------------------------------------------------------------------
# Orchestrator (Step 8)
# ---------------------------------------------------------------------------

def generate_all():
    """Generate complete SoSafe dataset and write to sosafe.db."""
    company = "sosafe"

    print("Generating accounts...")
    accounts = generate_accounts()
    write_df(accounts, "accounts", company)

    print("Generating subscriptions...")
    subscriptions = generate_subscriptions(accounts)
    write_df(subscriptions, "subscriptions", company)

    print("Generating feature activations...")
    activations = generate_feature_activations(accounts)
    write_df(activations, "feature_activations", company)

    print("Generating tenants...")
    tenants = generate_tenants(accounts, activations)
    write_df(tenants, "tenants", company)

    print("Generating users...")
    users = generate_users(accounts, tenants)
    write_df(users, "users", company)

    print("Generating campaigns...")
    campaigns = generate_campaigns(accounts)
    write_df(campaigns, "campaigns", company)

    print("Generating events (per-user expansion)...")
    events = generate_events(accounts, campaigns, activations, users)
    write_df(events, "events", company)

    # Print summary
    print("\n=== SoSafe Data Summary ===")
    for tier in PLAN_TIERS:
        tier_accts = accounts[accounts["plan_tier"] == tier]
        print(
            f"  {tier}: {len(tier_accts)} accounts, "
            f"avg ARR ${tier_accts['arr'].mean():,.0f}, "
            f"churn rate {tier_accts['churned'].mean():.0%}"
        )

    print(f"\nTotal accounts: {len(accounts)}")
    print(f"Total subscriptions: {len(subscriptions)}")
    print(
        f"Total feature activations: {len(activations)} "
        f"({activations['activated'].sum()} activated)"
    )
    print(f"Total tenants: {len(tenants)}")
    print(f"Total users: {len(users)}")
    print(f"Total campaigns: {len(campaigns)}")
    print(f"Total events: {len(events):,}")

    return {
        "accounts": accounts,
        "subscriptions": subscriptions,
        "activations": activations,
        "tenants": tenants,
        "users": users,
        "campaigns": campaigns,
        "events": events,
    }


if __name__ == "__main__":
    generate_all()
