"""NetworkX graph construction from SQLite data.

Follows reference's build_journey_graph() step by step:
  Reference: User nodes -> Product nodes -> Session+Event groupby -> temporal chain
  Ours: Account nodes -> Feature nodes -> Event groupby(account_id) -> temporal chain

Additional edges: Account->Feature, Account->Campaign, Account->Ticket, Ticket->Feature.
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


def build_journey_graph(company: str) -> nx.DiGraph:
    """Build a directed graph from SQLite tables.

    Node types: Account, Feature, Campaign, Event, Ticket
    Edge types: GENERATED, NEXT, ENTITLED_TO, ACTIVATED, RAN, PRODUCED,
                FILED, RELATES_TO
    """
    G = nx.DiGraph()

    # Load data
    accounts = read_df("accounts", company)
    activations = read_df("feature_activations", company)
    campaigns = read_df("campaigns", company)
    events = read_df("events", company)

    # Check for optional unstructured tables
    try:
        tickets = read_df("support_tickets", company)
    except Exception:
        tickets = pd.DataFrame()

    # --- Stage 1: Account nodes (like reference's User nodes) ---
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

    # --- Stage 2: Feature nodes (like reference's Product nodes) ---
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

    # --- Stage 5: Event nodes with temporal chain (like reference's Session+Event groupby) ---
    print("  Adding event nodes and temporal chains...")
    events_sorted = events.sort_values("timestamp")

    # Group events by account_id, build temporal chain per account
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
            if pd.notna(evt.get("count")):
                attrs["count"] = int(evt["count"])

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

            # Temporal chain: Event -> NEXT -> Event
            if prev_event_node is not None:
                G.add_edge(prev_event_node, evt_node, edge_type="NEXT")
            prev_event_node = evt_node

        if (int(account_id.split("-")[1]) % 50 == 0):
            print(f"    Processed events for {account_id}")

    # --- Stage 6: Ticket nodes and edges (if unstructured data exists) ---
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

            # Account -> Ticket edge
            if pd.notna(tkt.get("account_id")):
                G.add_edge(
                    f"account_{tkt['account_id']}", tkt_node,
                    edge_type="FILED",
                )

            # Ticket -> Feature edge (RELATES_TO via category lookup)
            category = tkt.get("category", "")
            category_map = CATEGORY_FEATURE_MAP.get(company, {})
            if category in category_map:
                for feat in category_map[category]:
                    feat_node = f"feature_{feat}"
                    if G.has_node(feat_node):
                        G.add_edge(tkt_node, feat_node, edge_type="RELATES_TO")

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
