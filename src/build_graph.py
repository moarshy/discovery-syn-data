"""NetworkX graph construction from SQLite data.

Follows reference's build_journey_graph() step by step:
  Reference: User nodes -> Product nodes -> Session+Event groupby -> temporal chain
  Ours: Account nodes -> Feature nodes -> Event groupby(account_id) -> temporal chain

Additional nodes: Tenant, User, Subscription, FeatureRequest
Additional edges: HAS_TENANT, BELONGS_TO, WORKS_IN, SUBSCRIBED, PERFORMED,
                  REQUESTED_BY, SUBMITTED, RELATES_TO (feature requests)
"""

import os
import pickle
import sys

import networkx as nx
import pandas as pd

from .db import read_df

GRAPH_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "graph")

# Maps ticket categories to related features for RELATES_TO edges
CATEGORY_FEATURE_MAP = {
    "sosafe": {
        "Integration Setup": ["sso", "scim"],
        "Report Button Installation": ["report_button"],
        "SSO/SCIM Setup": ["sso", "scim"],
        "Campaign Configuration": ["basic_phishing", "advanced_phishing", "elearning"],
        "Training Content": ["elearning"],
        "Dashboard/Analytics": ["human_risk_os"],
    },
    "synthflow": {
        "Agent Configuration": ["voice_agents", "custom_voices"],
        "CRM Integration": ["crm_integration"],
        "Telephony Setup": ["call_routing"],
        "Voice Cloning": ["custom_voices"],
        "API/Webhooks": ["api_access"],
        "Latency/Performance": ["voice_agents", "call_routing"],
        "Call Quality": ["voice_agents"],
    },
}

# Maps feature request categories to related features
FR_CATEGORY_FEATURE_MAP = {
    "sosafe": {
        "Reporting & Analytics": ["human_risk_os"],
        "Integration": ["sso", "scim"],
        "Compliance": ["human_risk_os", "advanced_phishing"],
        "Campaign Management": ["basic_phishing", "advanced_phishing"],
        "Content Library": ["elearning"],
        "Automation": ["sofie"],
        "API & Extensibility": ["sso", "scim"],
    },
    "synthflow": {
        "Voice Quality": ["voice_agents", "custom_voices"],
        "Integration": ["crm_integration"],
        "Analytics & Reporting": ["analytics_dashboard"],
        "Call Management": ["call_routing"],
        "Agent Builder": ["voice_agents"],
        "API & Webhooks": ["api_access"],
        "Multi-language": ["multi_language"],
    },
}


def _load_table_safe(table: str, company: str) -> pd.DataFrame:
    """Load a table, returning empty DataFrame if it doesn't exist."""
    try:
        return read_df(table, company)
    except Exception:
        return pd.DataFrame()


def build_journey_graph(company: str) -> nx.DiGraph:
    """Build a directed graph from SQLite tables.

    Node types: Account, Feature, Campaign, Event, Ticket, Tenant, User, Subscription, FeatureRequest
    Edge types: GENERATED, NEXT, ENTITLED_TO, ACTIVATED, RAN, PRODUCED,
                FILED, RELATES_TO, HAS_TENANT, BELONGS_TO, WORKS_IN,
                SUBSCRIBED, PERFORMED, REQUESTED_BY, SUBMITTED
    """
    G = nx.DiGraph()

    # Load data
    accounts = read_df("accounts", company)
    activations = read_df("feature_activations", company)
    campaigns = read_df("campaigns", company)
    events = read_df("events", company)

    # Optional tables
    tickets = _load_table_safe("support_tickets", company)
    tenants = _load_table_safe("tenants", company)
    users = _load_table_safe("users", company)
    subscriptions = _load_table_safe("subscriptions", company)
    feature_requests = _load_table_safe("feature_requests", company)

    # --- Stage 1: Account nodes ---
    print("  Adding account nodes...")
    for _, acct in accounts.iterrows():
        G.add_node(
            f"account_{acct['account_id']}",
            node_type="Account",
            account_id=acct["account_id"],
            name=acct["name"],
            plan_tier=acct["plan_tier"],
            arr=acct["arr"],
            employee_count=acct["employee_count"],
            industry=acct["industry"],
            country=acct["country"],
            churned=acct["churned"],
            churn_date=acct.get("churn_date"),
        )

    # --- Stage 2: Feature nodes ---
    print("  Adding feature nodes...")
    feature_names = activations["feature"].unique()
    for feat in feature_names:
        G.add_node(
            f"feature_{feat}",
            node_type="Feature",
            feature_name=feat,
        )

    # --- Stage 3: Feature entitlement and activation edges ---
    print("  Adding feature edges...")
    for _, act in activations.iterrows():
        acct_node = f"account_{act['account_id']}"
        feat_node = f"feature_{act['feature']}"

        if act["entitled"]:
            G.add_edge(acct_node, feat_node, edge_type="ENTITLED_TO")
        if act["activated"]:
            G.add_edge(
                acct_node, feat_node,
                edge_type="ACTIVATED",
                activation_date=act.get("activation_date"),
            )

    # --- Stage 4: Campaign nodes and edges ---
    print("  Adding campaign nodes...")
    for _, cmp in campaigns.iterrows():
        cmp_node = f"campaign_{cmp['campaign_id']}"
        G.add_node(
            cmp_node,
            node_type="Campaign",
            campaign_id=cmp["campaign_id"],
            campaign_type=cmp["type"],
            launch_date=cmp["launch_date"],
            target_count=cmp["target_count"],
            status=cmp["status"],
        )
        G.add_edge(
            f"account_{cmp['account_id']}", cmp_node,
            edge_type="RAN",
        )

    # --- Stage 5: Event nodes with temporal chain ---
    print("  Adding event nodes and temporal chains...")
    events_sorted = events.sort_values("timestamp")

    for account_id, acct_events in events_sorted.groupby("account_id"):
        acct_events = acct_events.sort_values("timestamp")
        prev_event_node = None

        for order, (_, evt) in enumerate(acct_events.iterrows()):
            evt_node = f"event_{evt['event_id']}"
            attrs = {
                "node_type": "Event",
                "event_id": evt["event_id"],
                "event_type": evt["event_type"],
                "timestamp": evt["timestamp"],
            }
            if pd.notna(evt.get("campaign_id")):
                attrs["campaign_id"] = evt["campaign_id"]

            G.add_node(evt_node, **attrs)

            # Account -> Event edge
            G.add_edge(
                f"account_{account_id}", evt_node,
                edge_type="GENERATED",
                order=order,
            )

            # Campaign -> Event edge (if campaign event)
            if pd.notna(evt.get("campaign_id")):
                cmp_node = f"campaign_{evt['campaign_id']}"
                if G.has_node(cmp_node):
                    G.add_edge(cmp_node, evt_node, edge_type="PRODUCED")

            # User -> Event PERFORMED edge (if user_id present)
            if "user_id" in evt.index and pd.notna(evt.get("user_id")):
                user_node = f"user_{evt['user_id']}"
                if G.has_node(user_node):
                    G.add_edge(user_node, evt_node, edge_type="PERFORMED")

            # Temporal chain: Event -> NEXT -> Event
            if prev_event_node is not None:
                G.add_edge(prev_event_node, evt_node, edge_type="NEXT")
            prev_event_node = evt_node

        if (int(account_id.split("-")[1]) % 50 == 0):
            print(f"    Processed events for {account_id}")

    # --- Stage 6: Ticket nodes and edges ---
    if len(tickets) > 0:
        print("  Adding ticket nodes...")
        for _, tkt in tickets.iterrows():
            tkt_node = f"ticket_{tkt['ticket_id']}"
            G.add_node(
                tkt_node,
                node_type="Ticket",
                ticket_id=tkt["ticket_id"],
                category=tkt.get("category", ""),
                subject=tkt.get("subject", ""),
                priority=tkt.get("priority", ""),
                status=tkt.get("status", ""),
                created_at=tkt.get("created_at", ""),
            )

            if pd.notna(tkt.get("account_id")):
                G.add_edge(
                    f"account_{tkt['account_id']}", tkt_node,
                    edge_type="FILED",
                )

            category = tkt.get("category", "")
            category_map = CATEGORY_FEATURE_MAP.get(company, {})
            if category in category_map:
                for feat in category_map[category]:
                    feat_node = f"feature_{feat}"
                    if G.has_node(feat_node):
                        G.add_edge(tkt_node, feat_node, edge_type="RELATES_TO")

    # --- Stage 7: Tenant nodes and edges ---
    if len(tenants) > 0:
        print("  Adding tenant nodes...")
        for _, tnt in tenants.iterrows():
            tnt_node = f"tenant_{tnt['tenant_id']}"
            G.add_node(
                tnt_node,
                node_type="Tenant",
                tenant_id=tnt["tenant_id"],
                domain=tnt.get("domain", ""),
                created_at=tnt.get("created_at", ""),
                setup_completion=tnt.get("setup_completion", 0),
                environment=tnt.get("environment", ""),
                user_limit=tnt.get("user_limit", 0),
                active_users=tnt.get("active_users", 0),
            )

            # Account -> Tenant (HAS_TENANT)
            if pd.notna(tnt.get("account_id")):
                G.add_edge(
                    f"account_{tnt['account_id']}", tnt_node,
                    edge_type="HAS_TENANT",
                )

    # --- Stage 8: User nodes and edges ---
    if len(users) > 0:
        print("  Adding user nodes...")
        for _, usr in users.iterrows():
            usr_node = f"user_{usr['user_id']}"
            G.add_node(
                usr_node,
                node_type="User",
                user_id=usr["user_id"],
                name=usr.get("name", ""),
                role=usr.get("role", ""),
                department=usr.get("department", ""),
                status=usr.get("status", ""),
                created_at=usr.get("created_at", ""),
                last_active=usr.get("last_active", ""),
            )

            # User -> Account (BELONGS_TO)
            if pd.notna(usr.get("account_id")):
                G.add_edge(
                    usr_node, f"account_{usr['account_id']}",
                    edge_type="BELONGS_TO",
                )

            # User -> Tenant (WORKS_IN)
            if pd.notna(usr.get("tenant_id")) and usr.get("tenant_id"):
                tnt_node = f"tenant_{usr['tenant_id']}"
                if G.has_node(tnt_node):
                    G.add_edge(usr_node, tnt_node, edge_type="WORKS_IN")

    # --- Stage 9: Subscription nodes and edges ---
    if len(subscriptions) > 0:
        print("  Adding subscription nodes...")
        for _, sub in subscriptions.iterrows():
            sub_node = f"subscription_{sub['subscription_id']}"
            G.add_node(
                sub_node,
                node_type="Subscription",
                subscription_id=sub["subscription_id"],
                plan_tier=sub.get("plan_tier", ""),
                mrr=sub.get("mrr", 0),
                arr=sub.get("arr", 0),
                start_date=sub.get("start_date", ""),
                end_date=sub.get("end_date", ""),
                change_type=sub.get("change_type", ""),
                seats=sub.get("seats", 0),
            )

            # Account -> Subscription (SUBSCRIBED)
            if pd.notna(sub.get("account_id")):
                G.add_edge(
                    f"account_{sub['account_id']}", sub_node,
                    edge_type="SUBSCRIBED",
                )

    # --- Stage 10: Feature request nodes and edges ---
    if len(feature_requests) > 0:
        print("  Adding feature request nodes...")
        fr_category_map = FR_CATEGORY_FEATURE_MAP.get(company, {})

        for _, fr in feature_requests.iterrows():
            fr_node = f"feature_request_{fr['request_id']}"
            G.add_node(
                fr_node,
                node_type="FeatureRequest",
                request_id=fr["request_id"],
                title=fr.get("title", ""),
                category=fr.get("category", ""),
                priority=fr.get("priority", ""),
                status=fr.get("status", ""),
                votes=fr.get("votes", 0),
                submitted_at=fr.get("submitted_at", ""),
            )

            # Account -> FeatureRequest (REQUESTED_BY)
            if pd.notna(fr.get("account_id")):
                G.add_edge(
                    f"account_{fr['account_id']}", fr_node,
                    edge_type="REQUESTED_BY",
                )

            # User -> FeatureRequest (SUBMITTED)
            if pd.notna(fr.get("user_id")) and fr.get("user_id"):
                user_node = f"user_{fr['user_id']}"
                if G.has_node(user_node):
                    G.add_edge(user_node, fr_node, edge_type="SUBMITTED")

            # FeatureRequest -> Feature (RELATES_TO)
            category = fr.get("category", "")
            if category in fr_category_map:
                for feat in fr_category_map[category]:
                    feat_node = f"feature_{feat}"
                    if G.has_node(feat_node):
                        G.add_edge(fr_node, feat_node, edge_type="RELATES_TO")

    return G


# ---------------------------------------------------------------------------
# Stats, save/load (same pattern as reference)
# ---------------------------------------------------------------------------

def get_graph_stats(G: nx.DiGraph) -> dict:
    """Count nodes and edges by type."""
    node_types = {}
    for _, data in G.nodes(data=True):
        nt = data.get("node_type", "Unknown")
        node_types[nt] = node_types.get(nt, 0) + 1

    edge_types = {}
    for _, _, data in G.edges(data=True):
        et = data.get("edge_type", "Unknown")
        edge_types[et] = edge_types.get(et, 0) + 1

    return {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "node_types": node_types,
        "edge_types": edge_types,
    }


def print_graph_stats(G: nx.DiGraph):
    """Pretty-print graph statistics."""
    stats = get_graph_stats(G)
    print(f"\n=== Graph Statistics ===")
    print(f"Total nodes: {stats['total_nodes']:,}")
    print(f"Total edges: {stats['total_edges']:,}")
    print(f"\nNode types:")
    for nt, count in sorted(stats["node_types"].items()):
        print(f"  {nt}: {count:,}")
    print(f"\nEdge types:")
    for et, count in sorted(stats["edge_types"].items()):
        print(f"  {et}: {count:,}")


def save_graph(G: nx.DiGraph, path: str = None):
    """Save graph to pickle."""
    os.makedirs(GRAPH_DIR, exist_ok=True)
    if path is None:
        path = os.path.join(GRAPH_DIR, "graph.pkl")
    with open(path, "wb") as f:
        pickle.dump(G, f)
    print(f"Graph saved to {path}")


def load_graph(path: str = None) -> nx.DiGraph:
    """Load graph from pickle."""
    if path is None:
        path = os.path.join(GRAPH_DIR, "graph.pkl")
    with open(path, "rb") as f:
        return pickle.load(f)


def load_or_build_graph(company: str = "sosafe", force_rebuild: bool = False) -> nx.DiGraph:
    """Load graph from cache or build from SQLite."""
    graph_path = os.path.join(GRAPH_DIR, f"{company}_graph.pkl")

    if not force_rebuild and os.path.exists(graph_path):
        print(f"Loading cached graph from {graph_path}")
        return load_graph(graph_path)

    print(f"Building graph for {company}...")
    G = build_journey_graph(company)
    save_graph(G, graph_path)
    print_graph_stats(G)
    return G


if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "sosafe"
    G = load_or_build_graph(company, force_rebuild=True)
