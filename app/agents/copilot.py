import json
import logging
from typing import Dict, Any

from langchain_groq import ChatGroq
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool

from ..tools.wb_api import WorldBankAPI
from ..utils.config import GROQ_API_KEY, LLM_MODEL, MAX_CONTEXT_TOKENS
from ..utils.token_budget import TokenBudgetManager

logger = logging.getLogger(__name__)

wb_api    = WorldBankAPI()
token_mgr = TokenBudgetManager(max_tokens=MAX_CONTEXT_TOKENS)

# ──────────────────────────── TOOLS ────────────────────────────

@tool
async def get_indicator(country_code: str, indicator_code: str) -> str:
    """Fetch a World Bank indicator for a single country.
    Use for single-country queries.
    Args:
        country_code: ISO 2-letter code (e.g. 'IN', 'US', 'CN', 'BR')
        indicator_code: World Bank code (e.g. 'NY.GDP.PCAP.CD')
    Returns JSON with yearly data points.
    """
    result = await wb_api.fetch_indicator(country_code, indicator_code)
    return json.dumps(result, indent=2)


@tool
async def compare_countries(country_codes: str, indicator_code: str) -> str:
    """Compare a World Bank indicator across multiple countries simultaneously (parallel fetch).
    Prefer this over get_indicator when the user mentions more than one country.
    Args:
        country_codes: Comma-separated ISO codes (e.g. 'IN,CN,US,BR,DE')
        indicator_code: World Bank code (e.g. 'NY.GDP.PCAP.CD')
    Returns JSON with comparison data and speedup metrics.
    """
    codes  = [c.strip().upper() for c in country_codes.split(",") if c.strip()]
    result = await wb_api.compare_countries(codes, indicator_code)
    return json.dumps(result, indent=2)


@tool
async def search_indicators(query: str) -> str:
    """Search for World Bank indicator codes by keyword.
    Call this first when you do not know the exact indicator code.
    Args:
        query: Natural-language search term (e.g. 'GDP', 'literacy', 'CO2', 'unemployment')
    Returns a list of matching indicator IDs and names.
    """
    results = await wb_api.search_indicators(query)
    return json.dumps(results, indent=2)


# ──────────────────────────── SYSTEM PROMPT ────────────────────────────

_SYSTEM = (
    "You are a World Bank Research Copilot. You help users analyse global "
    "development data using real numbers from the World Bank API.\n\n"
    "RULES:\n"
    "1. ALWAYS use the tools to fetch real data — never invent numbers.\n"
    "2. For multi-country questions use compare_countries (parallel, faster).\n"
    "3. If you are unsure of the indicator code, call search_indicators first.\n"
    "4. Cite the indicator name, unit, and year range in every response.\n"
    "5. Give specific numbers and a short analytical summary.\n"
    "6. If data is missing for certain years or countries, say so.\n\n"
    "Country codes: IN=India CN=China US=USA BR=Brazil DE=Germany "
    "JP=Japan GB=UK FR=France NG=Nigeria ZA=South Africa "
    "RU=Russia AU=Australia CA=Canada KR=South Korea MX=Mexico"
)


# ──────────────────────────── COPILOT ────────────────────────────

class WorldBankCopilot:
    def __init__(self):
        # ChatGroq has native Groq tool-calling support — more reliable than
        # the OpenAI-compatible shim for function calling with Llama models.
        self.llm = ChatGroq(
            model=LLM_MODEL,
            api_key=GROQ_API_KEY,
            temperature=0.1,
            max_retries=2,
        )
        self.tools = [get_indicator, compare_countries, search_indicators]
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_openai_tools_agent(self.llm, self.tools, self.prompt)
        self.executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=6,
            handle_parsing_errors=True,
            return_intermediate_steps=False,
        )

        # Plain LLM (no tools) used as a fallback if tool-calling fails
        self._plain_llm = ChatGroq(
            model=LLM_MODEL,
            api_key=GROQ_API_KEY,
            temperature=0.2,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def research(self, query: str) -> Dict[str, Any]:
        """Run an agent-powered research query with automatic fallback."""
        try:
            result = await self.executor.ainvoke({"input": query})
            return {
                "query":    query,
                "analysis": result.get("output", "No analysis generated."),
                "metrics":  wb_api.get_metrics(),
            }

        except Exception as agent_err:
            logger.warning(f"Agent failed ({agent_err}), falling back to direct LLM.")
            return await self._fallback(query, str(agent_err))

    async def _fallback(self, query: str, agent_error: str) -> Dict[str, Any]:
        """Direct LLM call without tool use — used when the agent fails."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            fallback_prompt = (
                f"{_SYSTEM}\n\n"
                "NOTE: The tool-calling agent could not run right now. "
                "Answer as best you can from your training knowledge, "
                "and clearly note that live World Bank data could not be fetched "
                "for this response. Suggest the user rephrase if the answer seems incomplete.\n\n"
                f"Question: {query}"
            )
            response = await self._plain_llm.ainvoke([HumanMessage(content=fallback_prompt)])
            return {
                "query":    query,
                "analysis": response.content,
                "metrics":  wb_api.get_metrics(),
                "fallback": True,
            }
        except Exception as fallback_err:
            logger.error(f"Fallback also failed: {fallback_err}")
            return {
                "query":    query,
                "analysis": (
                    "Sorry, I could not process your request right now. "
                    "Please check that your GROQ_API_KEY is set in .env and try again."
                ),
                "error": True,
            }


# ──────────────────────────── MANUAL TEST ────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def main():
        copilot = WorldBankCopilot()
        print("Copilot ready.")
        result = await copilot.research(
            "Compare the GDP per capita of India, China, and USA over the last 10 years"
        )
        print("\n=== Analysis ===")
        print(result["analysis"])
        print("\n=== Metrics ===")
        print(json.dumps(result.get("metrics", {}), indent=2))

    asyncio.run(main())
