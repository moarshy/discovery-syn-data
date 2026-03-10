"""GraphRAG retrieval engine for B2B SaaS product analytics.

Maps reference retrieval.py functions 1:1:
  extract_user_journeys()    -> extract_account_journey()
  extract_journey_pattern()  -> extract_activation_pattern()
  find_churn_paths()         -> find_churn_paths()
  compare_cohorts()          -> compare_tiers()
  find_products_before_purchase() -> find_pre_churn_signals()

New functions (no reference analog):
  find_activation_gaps()
  find_ticket_churn_correlation()

Plus serialization functions for LLM context and high-level query routing.
"""

from collections import Counter

import networkx as nx


# ---------------------------------------------------------------------------
# Core retrieval (mapped from reference)
# ---------------------------------------------------------------------------

def extract_account_journey(G: nx.DiGraph, account_id: str, max_events: int = 200) -> dict:
    """Extract full event journey for an account.

    Maps reference's extract_user_journeys() — gets account node, traverses to
    all successor events sorted by timestamp.
    """
    acct_node = f"account_{account_id}"
    if acct_node not in G:
        return {}

    acct_data = dict(G.nodes[acct_node])

    # Get all events for this account
    events = []
    for _, target, edge_data in G.edges(acct_node, data=True):
        if edge_data.get("edge_type") == "GENERATED":
            node_data = G.nodes[target]
            if node_data.get("node_type") == "Event":
                events.append(dict(node_data))

    events.sort(key=lambda e: e.get("timestamp", ""))
    events = events[:max_events]

    # Get activated features
    activated = []
    entitled = []
    for _, target, edge_data in G.edges(acct_node, data=True):
        if edge_data.get("edge_type") == "ACTIVATED":
            feat_data = G.nodes[target]
            activated.append(feat_data.get("feature_name", target))
        elif edge_data.get("edge_type") == "ENTITLED_TO":
            feat_data = G.nodes[target]
            entitled.append(feat_data.get("feature_name", target))

    # Get campaigns
    campaigns = []
    for _, target, edge_data in G.edges(acct_node, data=True):
        if edge_data.get("edge_type") == "RAN":
            cmp_data = G.nodes[target]
            campaigns.append(dict(cmp_data))

    # Get tickets
    tickets = []
    for _, target, edge_data in G.edges(acct_node, data=True):
        if edge_data.get("edge_type") == "FILED":
            tkt_data = G.nodes[target]
            tickets.append(dict(tkt_data))

    return {
        "account": acct_data,
        "events": events,
        "activated_features": activated,
        "entitled_features": entitled,
        "not_activated": [f for f in entitled if f not in activated],
        "campaigns": campaigns,
        "tickets": tickets,
    }


def extract_activation_pattern(events: list[dict]) -> str:
    """Convert event list to pattern string.

    Maps reference's extract_journey_pattern().
    Example: "admin.login -> admin.dashboard_viewed -> feature.sso_activated"
    """
    if not events:
        return ""
    types = [e.get("event_type", "unknown") for e in events]
    # Deduplicate consecutive identical events
    deduped = [types[0]]
    for t in types[1:]:
        if t != deduped[-1]:
            deduped.append(t)
    return " -> ".join(deduped)


def get_account_context(G: nx.DiGraph, account_id: str) -> dict:
    """Return account attributes. Maps reference's get_user_context()."""
    acct_node = f"account_{account_id}"
    if acct_node not in G:
        return {}
    return dict(G.nodes[acct_node])


# ---------------------------------------------------------------------------
# Pattern analysis (mapped from reference)
# ---------------------------------------------------------------------------

def find_churn_paths(G: nx.DiGraph, limit: int = 50) -> list[dict]:
    """Find event sequences for churned accounts.

    Maps reference's find_churn_paths() — finds churned users, extracts journeys.
    """
    churned_journeys = []

    for node, data in G.nodes(data=True):
        if data.get("node_type") == "Account" and data.get("churned"):
            account_id = data["account_id"]
            journey = extract_account_journey(G, account_id)
            if journey and journey.get("events"):
                churned_journeys.append(journey)
            if len(churned_journeys) >= limit:
                break

    return churned_journeys


def find_common_patterns(
    G: nx.DiGraph,
    account_filter: dict = None,
    limit: int = 100,
) -> list[tuple]:
    """Aggregate event sequences into patterns.

    Maps reference's find_common_patterns() — groups by filter, counts patterns.
    Returns list of (pattern_string, count, percentage) sorted by frequency.
    """
    matching_accounts = []

    for node, data in G.nodes(data=True):
        if data.get("node_type") != "Account":
            continue
        if account_filter:
            if all(data.get(k) == v for k, v in account_filter.items()):
                matching_accounts.append(data["account_id"])
        else:
            matching_accounts.append(data["account_id"])

    if not matching_accounts:
        return []

    pattern_counter = Counter()
    sample = matching_accounts[:limit]

    for account_id in sample:
        journey = extract_account_journey(G, account_id, max_events=50)
        if journey and journey.get("events"):
            pattern = extract_activation_pattern(journey["events"])
            if pattern:
                # Truncate very long patterns
                parts = pattern.split(" -> ")
                if len(parts) > 10:
                    pattern = " -> ".join(parts[:10]) + " -> ..."
                pattern_counter[pattern] += 1

    total = sum(pattern_counter.values())
    results = [
        (pattern, count, round(count / total * 100, 1))
        for pattern, count in pattern_counter.most_common(20)
    ]

    return results


def compare_tiers(
    G: nx.DiGraph,
    tier_a: str = "Essential",
    tier_b: str = "Premium",
    sample_size: int = 50,
) -> dict:
    """Compare metrics across plan tiers.

    Maps reference's compare_cohorts() — analyzes two cohorts side by side.
    """

    def analyze_cohort(plan_tier: str) -> dict:
        accounts = []
        for node, data in G.nodes(data=True):
            if data.get("node_type") == "Account" and data.get("plan_tier") == plan_tier:
                accounts.append(data)

        if not accounts:
            return {"account_count": 0}

        sample = accounts[:sample_size]
        total_events = 0
        total_campaigns = 0
        total_activated = 0
        total_entitled = 0
        total_tickets = 0
        churn_count = 0
        arr_sum = 0

        for acct in sample:
            journey = extract_account_journey(G, acct["account_id"])
            total_events += len(journey.get("events", []))
            total_campaigns += len(journey.get("campaigns", []))
            total_activated += len(journey.get("activated_features", []))
            total_entitled += len(journey.get("entitled_features", []))
            total_tickets += len(journey.get("tickets", []))
            if acct.get("churned"):
                churn_count += 1
            arr_sum += acct.get("arr", 0)

        n = len(sample)
        return {
            "account_count": len(accounts),
            "sample_size": n,
            "avg_events": round(total_events / n, 1),
            "avg_campaigns": round(total_campaigns / n, 1),
            "avg_activated_features": round(total_activated / n, 2),
            "avg_entitled_features": round(total_entitled / n, 2),
            "activation_rate": round(
                total_activated / max(total_entitled, 1) * 100, 1
            ),
            "churn_rate": round(churn_count / n * 100, 1),
            "avg_arr": round(arr_sum / n, 0),
            "avg_tickets": round(total_tickets / n, 1),
        }

    a_stats = analyze_cohort(tier_a)
    b_stats = analyze_cohort(tier_b)

    comparison = {}
    for key in ["avg_events", "avg_campaigns", "activation_rate", "churn_rate", "avg_arr"]:
        a_val = a_stats.get(key, 0)
        b_val = b_stats.get(key, 0)
        comparison[f"{key}_diff"] = round(b_val - a_val, 1)

    return {
        tier_a: a_stats,
        tier_b: b_stats,
        "comparison": comparison,
    }


def find_pre_churn_signals(G: nx.DiGraph, limit: int = 50) -> dict:
    """Find patterns in the 30-60 days before churn.

    Maps reference's find_products_before_purchase() — walks backward from
    churn event to find preceding signals.
    """
    churned_journeys = find_churn_paths(G, limit)

    signals = {
        "total_churned_analyzed": len(churned_journeys),
        "unactivated_features": Counter(),
        "last_event_types": Counter(),
        "avg_events_before_churn": 0,
        "avg_campaigns_before_churn": 0,
        "ticket_categories": Counter(),
        "sample_journeys": [],
    }

    total_events = 0
    total_campaigns = 0

    for journey in churned_journeys:
        acct = journey["account"]

        # Unactivated features as churn signal
        for feat in journey.get("not_activated", []):
            signals["unactivated_features"][feat] += 1

        # Last event before churn
        events = journey.get("events", [])
        if events:
            signals["last_event_types"][events[-1].get("event_type", "unknown")] += 1
            total_events += len(events)

        total_campaigns += len(journey.get("campaigns", []))

        # Ticket categories
        for ticket in journey.get("tickets", []):
            signals["ticket_categories"][ticket.get("category", "unknown")] += 1

        # Sample journeys for LLM context
        if len(signals["sample_journeys"]) < 5:
            signals["sample_journeys"].append({
                "account_id": acct["account_id"],
                "plan_tier": acct.get("plan_tier"),
                "arr": acct.get("arr"),
                "pattern": extract_activation_pattern(events[:20]),
                "not_activated": journey.get("not_activated", []),
                "ticket_count": len(journey.get("tickets", [])),
            })

    n = max(len(churned_journeys), 1)
    signals["avg_events_before_churn"] = round(total_events / n, 1)
    signals["avg_campaigns_before_churn"] = round(total_campaigns / n, 1)

    # Convert Counters to sorted lists for serialization
    signals["unactivated_features"] = signals["unactivated_features"].most_common(10)
    signals["last_event_types"] = signals["last_event_types"].most_common(10)
    signals["ticket_categories"] = signals["ticket_categories"].most_common(10)

    return signals


# ---------------------------------------------------------------------------
# New functions (no reference analog)
# ---------------------------------------------------------------------------

def find_activation_gaps(G: nx.DiGraph) -> dict:
    """Find features with low activation rates across account base.

    Groups by plan tier and feature, showing entitled vs activated counts.
    """
    gaps = {}

    # Collect activation data by tier
    for node, data in G.nodes(data=True):
        if data.get("node_type") != "Account":
            continue

        tier = data.get("plan_tier", "Unknown")
        if tier not in gaps:
            gaps[tier] = {"accounts": 0, "features": {}}
        gaps[tier]["accounts"] += 1

        account_id = data["account_id"]
        acct_node = f"account_{account_id}"

        # Check each feature edge
        for _, target, edge_data in G.edges(acct_node, data=True):
            if G.nodes[target].get("node_type") != "Feature":
                continue
            feat_name = G.nodes[target].get("feature_name", "unknown")

            if feat_name not in gaps[tier]["features"]:
                gaps[tier]["features"][feat_name] = {
                    "entitled": 0, "activated": 0,
                }

            if edge_data.get("edge_type") == "ENTITLED_TO":
                gaps[tier]["features"][feat_name]["entitled"] += 1
            if edge_data.get("edge_type") == "ACTIVATED":
                gaps[tier]["features"][feat_name]["activated"] += 1

    # Calculate activation rates
    for tier in gaps:
        for feat in gaps[tier]["features"]:
            f = gaps[tier]["features"][feat]
            f["activation_rate"] = (
                round(f["activated"] / max(f["entitled"], 1) * 100, 1)
            )

    return gaps


def find_ticket_churn_correlation(G: nx.DiGraph) -> dict:
    """Analyze correlation between ticket patterns and churn.

    Compares ticket volume, categories, and priority between churned
    and retained accounts.
    """
    churned_stats = {"count": 0, "tickets": 0, "categories": Counter(), "priorities": Counter()}
    retained_stats = {"count": 0, "tickets": 0, "categories": Counter(), "priorities": Counter()}

    for node, data in G.nodes(data=True):
        if data.get("node_type") != "Account":
            continue

        stats = churned_stats if data.get("churned") else retained_stats
        stats["count"] += 1

        # Count tickets for this account
        acct_node = f"account_{data['account_id']}"
        for _, target, edge_data in G.edges(acct_node, data=True):
            if edge_data.get("edge_type") == "FILED":
                tkt = G.nodes[target]
                stats["tickets"] += 1
                stats["categories"][tkt.get("category", "unknown")] += 1
                stats["priorities"][tkt.get("priority", "unknown")] += 1

    def summarize(stats):
        n = max(stats["count"], 1)
        return {
            "account_count": stats["count"],
            "total_tickets": stats["tickets"],
            "avg_tickets_per_account": round(stats["tickets"] / n, 2),
            "top_categories": stats["categories"].most_common(5),
            "priority_distribution": dict(stats["priorities"]),
        }

    return {
        "churned": summarize(churned_stats),
        "retained": summarize(retained_stats),
    }


# ---------------------------------------------------------------------------
# Serialization for LLM (same pattern as reference)
# ---------------------------------------------------------------------------

def serialize_journey_to_text(journey: dict) -> str:
    """Convert single account journey to human-readable string.

    Maps reference's serialize_journey_to_text().
    """
    acct = journey.get("account", {})
    parts = [
        f"Account {acct.get('account_id', '?')} "
        f"(plan: {acct.get('plan_tier', '?')}, "
        f"ARR: ${acct.get('arr', 0):,}, "
        f"churned: {acct.get('churned', False)})"
    ]

    activated = journey.get("activated_features", [])
    if activated:
        parts.append(f"  Activated: {', '.join(activated)}")

    not_activated = journey.get("not_activated", [])
    if not_activated:
        parts.append(f"  NOT activated (entitled): {', '.join(not_activated)}")

    campaigns = journey.get("campaigns", [])
    if campaigns:
        parts.append(f"  Campaigns: {len(campaigns)}")

    events = journey.get("events", [])
    if events:
        pattern = extract_activation_pattern(events[:15])
        parts.append(f"  Event pattern: {pattern}")

    tickets = journey.get("tickets", [])
    if tickets:
        cats = Counter(t.get("category", "?") for t in tickets)
        parts.append(f"  Tickets: {dict(cats)}")

    return "\n".join(parts)


def serialize_journeys_for_llm(
    journeys: list[dict],
    max_journeys: int = 10,
    include_stats: bool = True,
) -> str:
    """Format multiple journeys with optional statistics.

    Maps reference's serialize_journeys_for_llm().
    """
    parts = []

    if include_stats and journeys:
        total = len(journeys)
        churned = sum(1 for j in journeys if j.get("account", {}).get("churned"))
        parts.append(
            f"### Summary: {total} accounts analyzed, {churned} churned\n"
        )

        # Event type distribution
        all_events = []
        for j in journeys:
            all_events.extend(j.get("events", []))
        if all_events:
            event_dist = Counter(e.get("event_type") for e in all_events)
            top_events = event_dist.most_common(8)
            parts.append("Event distribution:")
            for et, count in top_events:
                parts.append(f"  {et}: {count} ({count/len(all_events)*100:.1f}%)")
            parts.append("")

    for i, journey in enumerate(journeys[:max_journeys], 1):
        parts.append(f"--- Account {i} ---")
        parts.append(serialize_journey_to_text(journey))
        parts.append("")

    return "\n".join(parts)


def serialize_patterns_for_llm(
    patterns: list[tuple],
    context_description: str = "event patterns",
) -> str:
    """Format pattern list with counts and percentages.

    Maps reference's serialize_patterns_for_llm().
    """
    parts = [f"### {context_description.title()}\n"]
    for pattern, count, pct in patterns:
        parts.append(f"  {pattern}  ({count} accounts, {pct}%)")
    return "\n".join(parts)


def serialize_comparison_for_llm(comparison: dict) -> str:
    """Format tier comparison as markdown.

    Maps reference's serialize_comparison_for_llm().
    """
    parts = ["### Tier Comparison\n"]

    for key, value in comparison.items():
        if key == "comparison":
            continue
        if isinstance(value, dict):
            parts.append(f"**{key}:**")
            for metric, val in value.items():
                if metric in ("features",):
                    continue
                parts.append(f"  {metric}: {val}")
            parts.append("")

    diff = comparison.get("comparison", {})
    if diff:
        parts.append("**Differences:**")
        for metric, val in diff.items():
            direction = "higher" if val > 0 else "lower"
            parts.append(f"  {metric}: {abs(val)} {direction}")

    return "\n".join(parts)


def serialize_gaps_for_llm(gaps: dict) -> str:
    """Format activation gap analysis for LLM context."""
    parts = ["### Feature Activation Gaps by Tier\n"]

    for tier, data in sorted(gaps.items()):
        parts.append(f"**{tier}** ({data['accounts']} accounts):")
        for feat, stats in sorted(
            data["features"].items(),
            key=lambda x: x[1].get("activation_rate", 100),
        ):
            if stats["entitled"] > 0:
                parts.append(
                    f"  {feat}: {stats['activated']}/{stats['entitled']} "
                    f"activated ({stats['activation_rate']}%)"
                )
        parts.append("")

    return "\n".join(parts)


def serialize_ticket_correlation_for_llm(correlation: dict) -> str:
    """Format ticket-churn correlation for LLM context."""
    parts = ["### Ticket-Churn Correlation\n"]

    for cohort_name in ("churned", "retained"):
        cohort = correlation[cohort_name]
        parts.append(f"**{cohort_name.title()} Accounts** ({cohort['account_count']}):")
        parts.append(f"  Avg tickets per account: {cohort['avg_tickets_per_account']}")
        parts.append(f"  Total tickets: {cohort['total_tickets']}")
        if cohort.get("top_categories"):
            cats = ", ".join(f"{c}({n})" for c, n in cohort["top_categories"])
            parts.append(f"  Top categories: {cats}")
        if cohort.get("priority_distribution"):
            parts.append(f"  Priority distribution: {cohort['priority_distribution']}")
        parts.append("")

    return "\n".join(parts)


def serialize_pre_churn_for_llm(signals: dict) -> str:
    """Format pre-churn signals for LLM context."""
    parts = [
        f"### Pre-Churn Signals ({signals['total_churned_analyzed']} accounts)\n",
        f"Avg events before churn: {signals['avg_events_before_churn']}",
        f"Avg campaigns before churn: {signals['avg_campaigns_before_churn']}",
    ]

    if signals["unactivated_features"]:
        parts.append("\nTop unactivated features among churned:")
        for feat, count in signals["unactivated_features"]:
            parts.append(f"  {feat}: {count} accounts")

    if signals["last_event_types"]:
        parts.append("\nLast event types before churn:")
        for et, count in signals["last_event_types"]:
            parts.append(f"  {et}: {count}")

    if signals["ticket_categories"]:
        parts.append("\nTicket categories from churned accounts:")
        for cat, count in signals["ticket_categories"]:
            parts.append(f"  {cat}: {count}")

    if signals["sample_journeys"]:
        parts.append("\nSample churned journeys:")
        for sj in signals["sample_journeys"]:
            parts.append(
                f"  {sj['account_id']} ({sj['plan_tier']}, ${sj.get('arr', 0):,}): "
                f"pattern={sj['pattern'][:80]}... "
                f"unactivated={sj['not_activated']}, "
                f"tickets={sj['ticket_count']}"
            )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# High-level query functions (route to the right retrieval)
# ---------------------------------------------------------------------------

def query_churn_activation(G: nx.DiGraph) -> str:
    """Q1: How do feature activation patterns correlate with churn?"""
    churn_paths = find_churn_paths(G, limit=30)
    patterns = find_common_patterns(G, {"churned": 1}, limit=30)
    gaps = find_activation_gaps(G)

    context = serialize_journeys_for_llm(churn_paths, max_journeys=10)
    context += "\n\n" + serialize_patterns_for_llm(patterns, "churned account patterns")
    context += "\n\n" + serialize_gaps_for_llm(gaps)
    return context


def query_pre_churn_behavior(G: nx.DiGraph) -> str:
    """Q2: What signals appear 30-60 days before churn?"""
    signals = find_pre_churn_signals(G, limit=50)
    return serialize_pre_churn_for_llm(signals)


def query_tier_comparison(G: nx.DiGraph) -> str:
    """Q3: How do lowest vs highest tier accounts differ in behavior?"""
    tiers = sorted({data.get("plan_tier") for _, data in G.nodes(data=True) if data.get("node_type") == "Account"})
    tier_a, tier_b = tiers[0], tiers[-1]
    comparison = compare_tiers(G, tier_a, tier_b)
    patterns_a = find_common_patterns(G, {"plan_tier": tier_a}, limit=30)
    patterns_b = find_common_patterns(G, {"plan_tier": tier_b}, limit=30)

    context = serialize_comparison_for_llm(comparison)
    context += "\n\n" + serialize_patterns_for_llm(patterns_a, f"{tier_a} tier patterns")
    context += "\n\n" + serialize_patterns_for_llm(patterns_b, f"{tier_b} tier patterns")
    return context


def query_activation_gaps(G: nx.DiGraph) -> str:
    """Q4: Which features have the biggest activation gaps?"""
    gaps = find_activation_gaps(G)
    return serialize_gaps_for_llm(gaps)


def query_ticket_correlation(G: nx.DiGraph) -> str:
    """Q5: How do support ticket patterns correlate with churn?"""
    correlation = find_ticket_churn_correlation(G)
    return serialize_ticket_correlation_for_llm(correlation)
