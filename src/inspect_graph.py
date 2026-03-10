"""Interactive graph visualization with pyvis.

Three views:
  account   — One account's full neighborhood (features, campaigns, tickets, events)
  landscape — All accounts ↔ features, colored by churn/tier (~208 nodes)
  churn     — Churned accounts only, with their features and tickets

Usage:
  python -m src.inspect_graph landscape              # default: all accounts ↔ features
  python -m src.inspect_graph account ACC-0042        # one account's neighborhood
  python -m src.inspect_graph churn                   # churned accounts focus
"""

import os
import sys

from pyvis.network import Network

from .build_graph import load_or_build_graph

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "graph")

# Color palette
COLORS = {
    # Node types
    "Account_retained": "#4CAF50",   # green
    "Account_churned": "#F44336",    # red
    "Feature": "#2196F3",            # blue
    "Campaign_phishing": "#FF9800",  # orange
    "Campaign_elearning": "#9C27B0", # purple
    "Ticket": "#FFC107",             # amber
    "Event": "#78909C",              # blue-grey
    # Edge types
    "ACTIVATED": "#4CAF50",
    "ENTITLED_TO": "#90CAF9",
    "FILED": "#FFC107",
    "RELATES_TO": "#F44336",
    "RAN": "#BDBDBD",
    "GENERATED": "#CFD8DC",
    "NEXT": "#B0BEC5",
}

TIER_SIZES = {
    "Essential": 15,
    "Professional": 20,
    "Premium": 28,
    "Ultimate": 35,
    "Starter": 15,
    "Growth": 22,
    "Enterprise": 30,
    "Agency": 35,
}


def _account_color(data):
    return COLORS["Account_churned"] if data.get("churned") else COLORS["Account_retained"]


def _account_title(data):
    """Hover tooltip for account nodes."""
    lines = [
        f"<b>{data.get('name', '?')}</b>",
        f"ID: {data.get('account_id', '?')}",
        f"Tier: {data.get('plan_tier', '?')}",
        f"ARR: ${data.get('arr', 0):,}",
        f"Employees: {data.get('employee_count', 0):,}",
        f"Industry: {data.get('industry', '?')}",
        f"Country: {data.get('country', '?')}",
        f"Churned: {'Yes' if data.get('churned') else 'No'}",
    ]
    if data.get("churn_date"):
        lines.append(f"Churn date: {data['churn_date']}")
    return "<br>".join(lines)


def _new_network(title, height="900px"):
    net = Network(
        height=height,
        width="100%",
        directed=True,
        notebook=False,
        bgcolor="#1a1a2e",
        font_color="#e0e0e0",
        heading="",
    )
    # Physics stabilizes the layout then turns off so nodes stop moving
    net.set_options("""
    {
      "physics": {
        "barnesHut": {
          "gravitationalConstant": -8000,
          "centralGravity": 0.1,
          "springLength": 250,
          "springConstant": 0.02,
          "damping": 0.15,
          "avoidOverlap": 0.5
        },
        "stabilization": {
          "enabled": true,
          "iterations": 500,
          "updateInterval": 25
        }
      }
    }
    """)
    # Inject title as HTML and disable physics after stabilization
    net.html = getattr(net, 'html', '')
    net._custom_title = title
    return net


def _write_html(net, output_path):
    """Write HTML with physics disabled after stabilization and a clean title."""
    net.write_html(output_path, open_browser=False)
    # Post-process: add title and disable physics after stabilize
    with open(output_path, "r") as f:
        html = f.read()
    # Remove ALL empty heading blocks pyvis generates (it creates two)
    import re
    html = re.sub(r'<center>\s*<h1>\s*</h1>\s*</center>', '', html)
    # Add our title
    title = getattr(net, '_custom_title', '')
    title_html = f'<h1 style="text-align:center;color:#e0e0e0;font-family:sans-serif;margin:12px 0 0 0;background:#1a1a2e;">{title}</h1>'
    html = html.replace("<body>", f"<body>\n{title_html}", 1)
    # Disable physics after stabilization so nodes stop bouncing
    stabilize_script = """
    <script>
    document.addEventListener("DOMContentLoaded", function() {
      // Find the network variable (pyvis names it 'network')
      var checkNet = setInterval(function() {
        if (typeof network !== 'undefined') {
          clearInterval(checkNet);
          network.on("stabilizationIterationsDone", function() {
            network.setOptions({ physics: false });
          });
        }
      }, 100);
    });
    </script>
    """
    html = html.replace("</body>", stabilize_script + "\n</body>", 1)
    with open(output_path, "w") as f:
        f.write(html)
    return output_path


# ---------------------------------------------------------------------------
# View 1: Feature landscape — all accounts ↔ features
# ---------------------------------------------------------------------------

def view_landscape(G, company="sosafe", output_path=None):
    """All accounts connected to features. ~208 nodes.

    Accounts colored by churn (red/green), sized by tier.
    Features are blue hubs. Edges: ACTIVATED (green) vs ENTITLED_TO (light blue).
    """
    net = _new_network(f"{company.title()} — Feature Activation Landscape")

    # Add feature nodes (central hubs)
    for node, data in G.nodes(data=True):
        if data.get("node_type") == "Feature":
            net.add_node(
                node,
                label=data["feature_name"],
                color=COLORS["Feature"],
                size=40,
                shape="diamond",
                title=f"<b>{data['feature_name']}</b>",
                font={"size": 16, "color": "#ffffff"},
            )

    # Add account nodes
    for node, data in G.nodes(data=True):
        if data.get("node_type") != "Account":
            continue
        tier = data.get("plan_tier", "Essential")
        net.add_node(
            node,
            label=data.get("account_id", "?"),
            color=_account_color(data),
            size=TIER_SIZES.get(tier, 15),
            shape="dot",
            title=_account_title(data),
        )

    # Add ENTITLED_TO and ACTIVATED edges
    for src, dst, edata in G.edges(data=True):
        etype = edata.get("edge_type")
        if etype == "ACTIVATED":
            net.add_edge(src, dst, color=COLORS["ACTIVATED"], width=2, title="ACTIVATED")
        elif etype == "ENTITLED_TO":
            net.add_edge(src, dst, color=COLORS["ENTITLED_TO"], width=1,
                         dashes=True, title="ENTITLED_TO (not activated)")

    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "landscape.html")
    _write_html(net, output_path)
    print(f"Landscape view saved to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# View 2: Single account neighborhood
# ---------------------------------------------------------------------------

def view_account(G, account_id, output_path=None, max_events=30):
    """One account's full neighborhood: features, campaigns, tickets, recent events."""
    acct_node = f"account_{account_id}"
    if acct_node not in G:
        print(f"Account {account_id} not found in graph")
        return None

    acct_data = G.nodes[acct_node]
    net = _new_network(
        f"Account {account_id} — {acct_data.get('name', '?')} "
        f"({acct_data.get('plan_tier', '?')}, "
        f"{'CHURNED' if acct_data.get('churned') else 'active'})"
    )

    # Add the account node (center)
    net.add_node(
        acct_node,
        label=f"{account_id}\n{acct_data.get('name', '?')}",
        color=_account_color(acct_data),
        size=50,
        shape="dot",
        title=_account_title(acct_data),
        font={"size": 14, "color": "#ffffff"},
    )

    # Collect neighbors by type
    events_to_add = []
    for _, target, edata in G.edges(acct_node, data=True):
        tdata = G.nodes[target]
        etype = edata.get("edge_type")
        ntype = tdata.get("node_type")

        if ntype == "Feature":
            color = COLORS["ACTIVATED"] if etype == "ACTIVATED" else COLORS["ENTITLED_TO"]
            dashes = etype != "ACTIVATED"
            net.add_node(
                target,
                label=tdata["feature_name"],
                color=COLORS["Feature"],
                size=30,
                shape="diamond",
                title=f"<b>{tdata['feature_name']}</b><br>Edge: {etype}",
                font={"size": 14, "color": "#ffffff"},
            )
            net.add_edge(acct_node, target, color=color, width=3,
                         dashes=dashes, title=etype, label=etype)

        elif ntype == "Campaign":
            ctype = tdata.get("campaign_type", "")
            color = COLORS["Campaign_phishing"] if "phishing" in ctype else COLORS["Campaign_elearning"]
            net.add_node(
                target,
                label=tdata.get("campaign_id", "?"),
                color=color,
                size=12,
                shape="triangle",
                title=(
                    f"<b>{tdata.get('campaign_id', '?')}</b><br>"
                    f"Type: {ctype}<br>"
                    f"Launch: {tdata.get('launch_date', '?')}<br>"
                    f"Targets: {tdata.get('target_count', '?')}"
                ),
            )
            net.add_edge(acct_node, target, color=COLORS["RAN"], width=1, title="RAN")

        elif ntype == "Ticket":
            net.add_node(
                target,
                label=tdata.get("ticket_id", "?"),
                color=COLORS["Ticket"],
                size=15,
                shape="square",
                title=(
                    f"<b>{tdata.get('ticket_id', '?')}</b><br>"
                    f"Category: {tdata.get('category', '?')}<br>"
                    f"Priority: {tdata.get('priority', '?')}<br>"
                    f"Subject: {tdata.get('subject', '?')}<br>"
                    f"Status: {tdata.get('status', '?')}"
                ),
            )
            net.add_edge(acct_node, target, color=COLORS["FILED"], width=2, title="FILED")

            # Ticket → Feature RELATES_TO edges
            for _, feat_target, feat_edata in G.edges(target, data=True):
                if feat_edata.get("edge_type") == "RELATES_TO":
                    feat_data = G.nodes[feat_target]
                    # Ensure feature node exists
                    if feat_target not in [n["id"] for n in net.nodes]:
                        net.add_node(
                            feat_target,
                            label=feat_data.get("feature_name", "?"),
                            color=COLORS["Feature"],
                            size=30,
                            shape="diamond",
                            font={"size": 14, "color": "#ffffff"},
                        )
                    net.add_edge(target, feat_target, color=COLORS["RELATES_TO"],
                                 width=1, dashes=True, title="RELATES_TO")

        elif ntype == "Event":
            events_to_add.append((target, tdata, edata))

    # Add limited events (most recent), with temporal chain
    events_to_add.sort(key=lambda x: x[1].get("timestamp", ""), reverse=True)
    event_nodes_added = set()
    for target, tdata, edata in events_to_add[:max_events]:
        net.add_node(
            target,
            label=tdata.get("event_type", "?").split(".")[-1],
            color=COLORS["Event"],
            size=8,
            shape="dot",
            title=(
                f"<b>{tdata.get('event_type', '?')}</b><br>"
                f"Time: {tdata.get('timestamp', '?')}<br>"
                f"Count: {tdata.get('count', 'N/A')}"
            ),
        )
        net.add_edge(acct_node, target, color=COLORS["GENERATED"], width=0.5,
                     hidden=True)  # hide GENERATED edges to reduce clutter
        event_nodes_added.add(target)

    # Add NEXT edges between the events we included
    for node_id in event_nodes_added:
        for _, next_node, edata in G.edges(node_id, data=True):
            if edata.get("edge_type") == "NEXT" and next_node in event_nodes_added:
                net.add_edge(node_id, next_node, color=COLORS["NEXT"], width=1,
                             arrows="to", title="NEXT")

    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, f"account_{account_id}.html")
    _write_html(net, output_path)
    print(f"Account view saved to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# View 3: Churn analysis — churned accounts with features and tickets
# ---------------------------------------------------------------------------

def view_churn(G, company="sosafe", output_path=None):
    """Churned accounts, their features (activated vs entitled), and tickets."""
    net = _new_network(f"{company.title()} — Churned Accounts: Features & Tickets")

    # Add feature nodes first
    for node, data in G.nodes(data=True):
        if data.get("node_type") == "Feature":
            net.add_node(
                node,
                label=data["feature_name"],
                color=COLORS["Feature"],
                size=40,
                shape="diamond",
                title=f"<b>{data['feature_name']}</b>",
                font={"size": 16, "color": "#ffffff"},
            )

    # Add churned accounts with their edges
    for node, data in G.nodes(data=True):
        if data.get("node_type") != "Account" or not data.get("churned"):
            continue

        tier = data.get("plan_tier", "Essential")
        net.add_node(
            node,
            label=data.get("account_id", "?"),
            color=COLORS["Account_churned"],
            size=TIER_SIZES.get(tier, 15),
            shape="dot",
            title=_account_title(data),
        )

        for _, target, edata in G.edges(node, data=True):
            etype = edata.get("edge_type")
            tdata = G.nodes[target]

            if etype == "ACTIVATED":
                net.add_edge(node, target, color=COLORS["ACTIVATED"], width=2,
                             title="ACTIVATED")
            elif etype == "ENTITLED_TO":
                net.add_edge(node, target, color=COLORS["ENTITLED_TO"], width=1,
                             dashes=True, title="ENTITLED_TO (not activated)")
            elif etype == "FILED" and tdata.get("node_type") == "Ticket":
                net.add_node(
                    target,
                    label=tdata.get("ticket_id", "?"),
                    color=COLORS["Ticket"],
                    size=10,
                    shape="square",
                    title=(
                        f"<b>{tdata.get('ticket_id', '?')}</b><br>"
                        f"Category: {tdata.get('category', '?')}<br>"
                        f"Priority: {tdata.get('priority', '?')}<br>"
                        f"Subject: {tdata.get('subject', '?')}"
                    ),
                )
                net.add_edge(node, target, color=COLORS["FILED"], width=1,
                             title="FILED")

                # Ticket → Feature
                for _, feat_target, feat_edata in G.edges(target, data=True):
                    if feat_edata.get("edge_type") == "RELATES_TO":
                        net.add_edge(target, feat_target, color=COLORS["RELATES_TO"],
                                     width=1, dashes=True, title="RELATES_TO")

    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "churn.html")
    _write_html(net, output_path)
    print(f"Churn view saved to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    company = args[0] if args else "sosafe"
    view = args[1] if len(args) > 1 else "landscape"
    # For backward compat: if first arg looks like a view name, treat it as such
    if company in ("landscape", "account", "churn"):
        view = company
        company = "sosafe"
        args = [company] + args  # shift args for account_id lookup

    G = load_or_build_graph(company)

    if view == "landscape":
        path = view_landscape(G, company)
    elif view == "account":
        account_id = args[2] if len(args) > 2 else "ACC-0001"
        path = view_account(G, account_id)
    elif view == "churn":
        path = view_churn(G, company)
    else:
        print(f"Unknown view: {view}")
        print("Usage: python -m src.inspect_graph [company] [landscape|account ACC-XXXX|churn]")
        return

    if path:
        print(f"\nOpen in browser: file://{os.path.abspath(path)}")


if __name__ == "__main__":
    main()
