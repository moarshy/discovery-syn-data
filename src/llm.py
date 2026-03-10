"""Claude API client for B2B SaaS product analysis.

Same JourneyLLM class interface as reference, adapted for Claude API.
anthropic.Anthropic replaces groq.Groq
response.content[0].text replaces response.choices[0].message.content
"""

import os

import anthropic

DEFAULT_MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are an expert B2B SaaS product analyst specializing in
customer journey analysis and product-led growth.

Your role is to:
- Analyze account-level behavioral data from graph-based retrieval
- Identify feature activation gaps, churn risk signals, and adoption patterns
- Compare cohorts across plan tiers, industries, and lifecycle stages
- Provide actionable product insights backed by specific data points

Guidelines:
- Be precise and cite specific patterns, percentages, and counts from the data
- Frame insights in product/business terms actionable for a PM or CS leader
- When comparing cohorts, highlight meaningful behavioral differences
- Suggest concrete interventions or experiments when appropriate
- Reference specific accounts or features when they illustrate a pattern
"""


class JourneyLLM:
    """LLM client for B2B SaaS product analysis.

    Same interface as reference's JourneyLLM but using Claude instead of Groq.
    """

    def __init__(self, api_key: str = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY must be set in environment or passed as argument"
            )
        self.model = model
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def generate(
        self,
        query: str,
        context: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """Generate analysis from query + retrieved context.

        Same interface as reference: constructs user message with context + question,
        sends to LLM with system prompt.
        """
        user_message = (
            f"## Account & Product Data Context:\n{context}\n\n"
            f"## Product Analysis Question:\n{query}"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        # Claude API: response.content[0].text (vs Groq: response.choices[0].message.content)
        return response.content[0].text

    def analyze_with_method(
        self,
        query: str,
        context: str,
        method: str = "graphrag",
        temperature: float = 0.3,
    ) -> dict:
        """Run analysis and return structured result with method metadata.

        Same interface as reference.
        """
        response = self.generate(query, context, temperature=temperature)
        return {
            "method": method,
            "query": query,
            "context": context,
            "response": response,
        }


# ---------------------------------------------------------------------------
# Convenience functions (same as reference)
# ---------------------------------------------------------------------------

def get_llm(api_key: str = None) -> JourneyLLM:
    """Return an initialized JourneyLLM instance."""
    return JourneyLLM(api_key=api_key)


def quick_analyze(query: str, context: str, api_key: str = None) -> str:
    """One-shot analysis: initialize LLM, generate, return response text."""
    llm = get_llm(api_key=api_key)
    return llm.generate(query, context)
