"""Comparison runner: 5 SoSafe questions through GraphRAG vs naive RAG.

Runs each question through both methods -> Claude analysis.
Prints side-by-side with heuristic scoring (stats cited, patterns found, actionability).
"""

import re
import sys
import time

from .build_graph import load_or_build_graph
from .llm import get_llm
from .naive_rag import load_or_build_naive_rag
from .retrieval import (
    query_activation_gaps,
    query_churn_activation,
    query_pre_churn_behavior,
    query_ticket_correlation,
    query_tier_comparison,
)

# Company-specific evaluation questions
COMPANY_QUESTIONS = {
    "sosafe": [
        {
            "id": "Q1",
            "query": "How do feature activation patterns correlate with churn? Which features have the lowest activation rates among churned accounts?",
            "retrieval_fn": "query_churn_activation",
        },
        {
            "id": "Q2",
            "query": "What behavioral signals appear 30-60 days before an account churns? Are there common event patterns that predict churn?",
            "retrieval_fn": "query_pre_churn_behavior",
        },
        {
            "id": "Q3",
            "query": "How do Essential tier accounts differ from Premium tier accounts in terms of feature usage, campaign activity, and churn risk?",
            "retrieval_fn": "query_tier_comparison",
        },
        {
            "id": "Q4",
            "query": "Which features have the biggest activation gaps across plan tiers? Where should the product team focus onboarding improvements?",
            "retrieval_fn": "query_activation_gaps",
        },
        {
            "id": "Q5",
            "query": "How do support ticket patterns (volume, categories, priority) correlate with churn outcomes? Are certain ticket types predictive?",
            "retrieval_fn": "query_ticket_correlation",
        },
    ],
    "synthflow": [
        {
            "id": "Q1",
            "query": "How do feature activation patterns correlate with churn? Which features have the lowest activation rates among churned accounts?",
            "retrieval_fn": "query_churn_activation",
        },
        {
            "id": "Q2",
            "query": "What behavioral signals appear 30-60 days before an account churns? Are there common event patterns that predict churn?",
            "retrieval_fn": "query_pre_churn_behavior",
        },
        {
            "id": "Q3",
            "query": "How do Starter tier accounts differ from Enterprise tier accounts in terms of feature usage, agent deployment activity, and churn risk?",
            "retrieval_fn": "query_tier_comparison",
        },
        {
            "id": "Q4",
            "query": "Which features have the biggest activation gaps across plan tiers? Where should the product team focus onboarding improvements?",
            "retrieval_fn": "query_activation_gaps",
        },
        {
            "id": "Q5",
            "query": "How do support ticket patterns (volume, categories, priority) correlate with churn outcomes? Are certain ticket types predictive?",
            "retrieval_fn": "query_ticket_correlation",
        },
    ],
}

RETRIEVAL_FN_MAP = {
    "query_churn_activation": query_churn_activation,
    "query_pre_churn_behavior": query_pre_churn_behavior,
    "query_tier_comparison": query_tier_comparison,
    "query_activation_gaps": query_activation_gaps,
    "query_ticket_correlation": query_ticket_correlation,
}

COMPANY_SCORE_PATTERNS = {
    "sosafe": r'report_button|sofie|sso|scim|human_risk_os|elearning|phishing|Essential|Professional|Premium|Ultimate',
    "synthflow": r'voice_agents|call_routing|crm_integration|analytics_dashboard|custom_voices|api_access|sla_support|multi_language|Starter|Growth|Enterprise|Agency',
}


def score_response(response: str, company: str = "sosafe") -> dict:
    """Heuristic scoring: stats cited, patterns found, actionability.

    GraphRAG responses should cite 3-5 specific stats per question vs naive RAG's 0-1.
    """
    # Count specific statistics (numbers, percentages, dollar amounts)
    stats_cited = len(re.findall(r'\d+\.?\d*%|\$[\d,]+|\d+ accounts?|\d+ tickets?', response))

    # Count specific feature/pattern mentions
    pattern = COMPANY_SCORE_PATTERNS.get(company, COMPANY_SCORE_PATTERNS["sosafe"])
    features_mentioned = len(re.findall(
        pattern,
        response, re.IGNORECASE,
    ))

    # Count actionable recommendations (look for imperative verbs, "should", "recommend")
    actionability = len(re.findall(
        r'should|recommend|consider|implement|prioritize|focus|invest|'
        r'improve|reduce|increase|target|automate',
        response, re.IGNORECASE,
    ))

    return {
        "stats_cited": stats_cited,
        "features_mentioned": features_mentioned,
        "actionability": actionability,
        "total": stats_cited + features_mentioned + actionability,
    }


def run_evaluation(company: str = "sosafe"):
    """Run all 5 questions through both methods and compare."""
    print(f"\n{'='*80}")
    print(f"  B2B SaaS GraphRAG vs Naive RAG Evaluation — {company}")
    print(f"{'='*80}\n")

    # Load resources
    print("Loading graph...")
    G = load_or_build_graph(company)

    print("Loading naive RAG index...")
    rag = load_or_build_naive_rag(company)

    print("Initializing LLM...")
    llm = get_llm()

    results = []
    questions = COMPANY_QUESTIONS.get(company, COMPANY_QUESTIONS["sosafe"])

    for q in questions:
        print(f"\n{'─'*80}")
        print(f"  {q['id']}: {q['query'][:70]}...")
        print(f"{'─'*80}")

        # GraphRAG retrieval + generation
        print(f"\n  [GraphRAG] Retrieving context...")
        retrieval_fn = RETRIEVAL_FN_MAP[q["retrieval_fn"]]
        graphrag_context = retrieval_fn(G)

        print(f"  [GraphRAG] Generating response...")
        t0 = time.time()
        graphrag_result = llm.analyze_with_method(
            q["query"], graphrag_context, method="graphrag",
        )
        graphrag_time = time.time() - t0

        # Naive RAG retrieval + generation
        print(f"  [Naive RAG] Retrieving context...")
        naive_context = rag.retrieve_context(q["query"], top_k=10)

        print(f"  [Naive RAG] Generating response...")
        t0 = time.time()
        naive_result = llm.analyze_with_method(
            q["query"], naive_context, method="naive_rag",
        )
        naive_time = time.time() - t0

        # Score both
        graphrag_score = score_response(graphrag_result["response"], company)
        naive_score = score_response(naive_result["response"], company)

        result = {
            "question": q,
            "graphrag": {
                "response": graphrag_result["response"],
                "context_length": len(graphrag_context),
                "time": round(graphrag_time, 1),
                "score": graphrag_score,
            },
            "naive": {
                "response": naive_result["response"],
                "context_length": len(naive_context),
                "time": round(naive_time, 1),
                "score": naive_score,
            },
        }
        results.append(result)

        # Print side-by-side comparison
        print(f"\n  {'GraphRAG':>40} | {'Naive RAG':<40}")
        print(f"  {'─'*40} | {'─'*40}")
        print(f"  {'Context length:':>20} {result['graphrag']['context_length']:>8} chars | "
              f"{'Context length:':<20} {result['naive']['context_length']:<8} chars")
        print(f"  {'Response time:':>20} {result['graphrag']['time']:>8}s | "
              f"{'Response time:':<20} {result['naive']['time']:<8}s")
        print(f"  {'Stats cited:':>20} {graphrag_score['stats_cited']:>8} | "
              f"{'Stats cited:':<20} {naive_score['stats_cited']:<8}")
        print(f"  {'Features mentioned:':>20} {graphrag_score['features_mentioned']:>8} | "
              f"{'Features mentioned:':<20} {naive_score['features_mentioned']:<8}")
        print(f"  {'Actionability:':>20} {graphrag_score['actionability']:>8} | "
              f"{'Actionability:':<20} {naive_score['actionability']:<8}")
        print(f"  {'TOTAL SCORE:':>20} {graphrag_score['total']:>8} | "
              f"{'TOTAL SCORE:':<20} {naive_score['total']:<8}")

        # Print truncated responses
        print(f"\n  --- GraphRAG Response (first 500 chars) ---")
        print(f"  {graphrag_result['response'][:500]}...")
        print(f"\n  --- Naive RAG Response (first 500 chars) ---")
        print(f"  {naive_result['response'][:500]}...")

    # Summary
    print(f"\n{'='*80}")
    print(f"  EVALUATION SUMMARY")
    print(f"{'='*80}")

    graphrag_wins = 0
    for r in results:
        g_total = r["graphrag"]["score"]["total"]
        n_total = r["naive"]["score"]["total"]
        winner = "GraphRAG" if g_total > n_total else "Naive RAG" if n_total > g_total else "Tie"
        if g_total > n_total:
            graphrag_wins += 1
        print(
            f"  {r['question']['id']}: GraphRAG={g_total} vs Naive={n_total} → {winner}"
        )

    print(f"\n  GraphRAG wins: {graphrag_wins}/{len(results)} questions")
    print(f"  Avg GraphRAG stats cited: "
          f"{sum(r['graphrag']['score']['stats_cited'] for r in results) / len(results):.1f}")
    print(f"  Avg Naive RAG stats cited: "
          f"{sum(r['naive']['score']['stats_cited'] for r in results) / len(results):.1f}")

    return results


if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "sosafe"
    run_evaluation(company)
