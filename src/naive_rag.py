"""Vector RAG baseline using sentence-transformers + FAISS.

Maps reference's session_to_document() to account_to_document().
~200 documents (one per account) vs reference's ~20K (one per session).
Same FAISS IndexFlatIP + sentence-transformers architecture.
"""

import os
import pickle
import sys

import faiss
import numpy as np
import pandas as pd

from .db import read_df

GRAPH_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "graph")


# ---------------------------------------------------------------------------
# Document generation (account_to_document replaces session_to_document)
# ---------------------------------------------------------------------------

def account_to_document(acct: pd.Series, activations_df: pd.DataFrame,
                        campaigns_df: pd.DataFrame, events_df: pd.DataFrame,
                        tickets_df: pd.DataFrame = None) -> str:
    """Convert an account's data to a single text document.

    Replaces reference's session_to_document() — account-level docs with plan,
    features, event summary, ticket summary.
    """
    parts = []

    # Account profile
    parts.append(
        f"Account {acct['account_id']} ({acct['name']}) | "
        f"Plan: {acct['plan_tier']} | ARR: ${acct['arr']:,} | "
        f"Industry: {acct['industry']} | Employees: {acct['employee_count']} | "
        f"Country: {acct['country']} | Churned: {bool(acct['churned'])}"
    )

    # Feature activations
    acct_acts = activations_df[activations_df["account_id"] == acct["account_id"]]
    activated = acct_acts[acct_acts["activated"] == 1]["feature"].tolist()
    entitled_not_activated = acct_acts[
        (acct_acts["entitled"] == 1) & (acct_acts["activated"] == 0)
    ]["feature"].tolist()

    if activated:
        parts.append(f"Activated features: {', '.join(activated)}")
    if entitled_not_activated:
        parts.append(f"Entitled but NOT activated: {', '.join(entitled_not_activated)}")

    # Campaign summary
    acct_campaigns = campaigns_df[campaigns_df["account_id"] == acct["account_id"]]
    if len(acct_campaigns) > 0:
        type_counts = acct_campaigns["type"].value_counts()
        campaign_summary = ", ".join(f"{count} {ctype}" for ctype, count in type_counts.items())
        parts.append(f"Campaigns: {campaign_summary}")

    # Event summary
    acct_events = events_df[events_df["account_id"] == acct["account_id"]]
    if len(acct_events) > 0:
        event_types = acct_events["event_type"].value_counts()
        top_events = ", ".join(
            f"{et}({c})" for et, c in event_types.head(5).items()
        )
        parts.append(f"Events ({len(acct_events)} total): {top_events}")

    # Ticket summary (if available)
    if tickets_df is not None and len(tickets_df) > 0:
        acct_tickets = tickets_df[tickets_df["account_id"] == acct["account_id"]]
        if len(acct_tickets) > 0:
            categories = acct_tickets["category"].value_counts()
            top_cats = ", ".join(
                f"{cat}({c})" for cat, c in categories.head(3).items()
            )
            parts.append(f"Tickets ({len(acct_tickets)} total): {top_cats}")

    return " | ".join(parts)


def generate_documents(company: str) -> list[dict]:
    """Generate one document per account.

    Returns list of dicts with text, account_id, plan_tier, churned.
    """
    accounts = read_df("accounts", company)
    activations = read_df("feature_activations", company)
    campaigns = read_df("campaigns", company)
    events = read_df("events", company)

    try:
        tickets = read_df("support_tickets", company)
    except Exception:
        tickets = None

    documents = []
    for _, acct in accounts.iterrows():
        text = account_to_document(acct, activations, campaigns, events, tickets)
        documents.append({
            "text": text,
            "account_id": acct["account_id"],
            "plan_tier": acct["plan_tier"],
            "churned": acct["churned"],
            "arr": acct["arr"],
        })

    return documents


# ---------------------------------------------------------------------------
# NaiveVectorRAG class (same architecture as reference)
# ---------------------------------------------------------------------------

class NaiveVectorRAG:
    """Vector RAG baseline using FAISS + sentence-transformers.

    Same interface as reference's NaiveVectorRAG class.
    """

    def __init__(self):
        self.model = None
        self.index = None
        self.documents = []
        self._initialized = False

    def _load_model(self):
        """Lazy-load sentence-transformer model."""
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def build_index(self, company: str):
        """Build FAISS index from account documents.

        Same flow as reference: generate docs -> encode -> normalize -> IndexFlatIP.
        """
        print("Generating documents...")
        self.documents = generate_documents(company)
        print(f"  {len(self.documents)} documents generated")

        print("Encoding documents...")
        self._load_model()
        texts = [d["text"] for d in self.documents]
        embeddings = self.model.encode(texts, show_progress_bar=True)
        embeddings = embeddings.astype(np.float32)

        # Normalize for cosine similarity (same as reference)
        faiss.normalize_L2(embeddings)

        # Create FAISS index
        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(embeddings)
        self._initialized = True

        print(f"  FAISS index built: {self.index.ntotal} vectors, dim={dim}")

    def save(self, path: str = None):
        """Save documents + FAISS index to pickle."""
        os.makedirs(GRAPH_DIR, exist_ok=True)
        if path is None:
            path = os.path.join(GRAPH_DIR, "naive_rag_index.pkl")
        data = {
            "documents": self.documents,
            "index_bytes": faiss.serialize_index(self.index),
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)
        print(f"Index saved to {path}")

    def load(self, path: str = None):
        """Load documents + FAISS index from pickle."""
        if path is None:
            path = os.path.join(GRAPH_DIR, "naive_rag_index.pkl")
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.documents = data["documents"]
        self.index = faiss.deserialize_index(data["index_bytes"])
        self._initialized = True
        print(f"Index loaded: {self.index.ntotal} vectors")

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Search for similar documents.

        Returns list of dicts with document data + similarity score.
        """
        if not self._initialized:
            raise RuntimeError("Index not built or loaded")

        self._load_model()
        query_vec = self.model.encode([query]).astype(np.float32)
        faiss.normalize_L2(query_vec)

        scores, indices = self.index.search(query_vec, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < len(self.documents):
                result = dict(self.documents[idx])
                result["similarity"] = float(score)
                results.append(result)

        return results

    def retrieve_context(self, query: str, top_k: int = 10) -> str:
        """Search and format results for LLM context.

        Same interface as reference.
        """
        results = self.search(query, top_k)
        if not results:
            return "No relevant accounts found."

        parts = [f"### Top {len(results)} Most Relevant Accounts\n"]
        for i, r in enumerate(results, 1):
            parts.append(
                f"**{i}. (similarity: {r['similarity']:.3f})**\n{r['text']}\n"
            )

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Convenience functions (same as reference)
# ---------------------------------------------------------------------------

def build_naive_rag(company: str, index_path: str = None) -> NaiveVectorRAG:
    """Build and save a naive RAG index."""
    rag = NaiveVectorRAG()
    rag.build_index(company)
    rag.save(index_path)
    return rag


def load_or_build_naive_rag(
    company: str = "sosafe",
    index_path: str = None,
    force_rebuild: bool = False,
) -> NaiveVectorRAG:
    """Load from cache or build fresh."""
    if index_path is None:
        index_path = os.path.join(GRAPH_DIR, f"{company}_naive_rag_index.pkl")

    rag = NaiveVectorRAG()
    if not force_rebuild and os.path.exists(index_path):
        print(f"Loading cached index from {index_path}")
        rag.load(index_path)
        return rag

    rag.build_index(company)
    rag.save(index_path)
    return rag


if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "sosafe"
    load_or_build_naive_rag(company, force_rebuild=True)
