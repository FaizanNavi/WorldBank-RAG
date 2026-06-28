import os
import json
import logging
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from ..tools.wb_api import WorldBankAPI
from ..utils.config import GROQ_API_KEY, LLM_MODEL, GROQ_BASE_URL, MAX_CONTEXT_TOKENS
from ..utils.token_budget import TokenBudgetManager
logger = logging.getLogger(__name__)
wb_api = WorldBankAPI()
token_mgr = TokenBudgetManager(max_tokens=MAX_CONTEXT_TOKENS)
@tool
async def get_indicator(country_code: str, indicator_code: str) -> str:
    result = await wb_api.fetch_indicator(country_code, indicator_code)
    return json.dumps(result, indent=2)
@tool
async def compare_countries(country_codes: str, indicator_code: str) -> str:
    codes = [c.strip().upper() for c in country_codes.split(",")]
    result = await wb_api.compare_countries(codes, indicator_code)
    return json.dumps(result, indent=2)
@tool
async def search_indicators(query: str) -> str:
    results = await wb_api.search_indicators(query)
    return json.dumps(results, indent=2)
class WorldBankCopilot:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=LLM_MODEL,
            openai_api_key=GROQ_API_KEY,
            openai_api_base=GROQ_BASE_URL,
            temperature=0.1,
        )
        self.tools = [get_indicator, compare_countries, search_indicators]
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "You are a World Bank Research Copilot. You help users analyze global "
             "development data from the World Bank.\n\n"
             "RULES:\n"
             "1. Always use the provided tools to fetch real data - never make up numbers.\n"
             "2. For multi-country comparisons, use compare_countries (it's parallel and faster).\n"
             "3. If you don't know the indicator code, use search_indicators first.\n"
             "4. Always cite the indicator name and time range in your response.\n"
             "5. Provide clear, data-driven analysis with specific numbers.\n"
             "6. If data is missing for some years, mention it.\n\n"
             "Common country codes: IN=India, CN=China, US=USA, BR=Brazil, "
             "DE=Germany, JP=Japan, NG=Nigeria, ZA=South Africa, GB=UK, FR=France"
            ),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        agent = create_openai_tools_agent(self.llm, self.tools, self.prompt)
        self.executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=5,
            handle_parsing_errors=True,
        )
    async def research(self, query: str) -> Dict[str, Any]:
        try:
            result = await self.executor.ainvoke({"input": query})
            return {
                "query": query,
                "analysis": result.get("output", "No analysis generated."),
                "metrics": wb_api.get_metrics()
            }
        except Exception as e:
            logger.error(f"Research error: {e}")
            return {
                "query": query,
                "analysis": f"Error processing your question: {str(e)}",
                "error": True
            }
if __name__ == "__main__":
    import asyncio
    async def main():
        copilot = WorldBankCopilot()
        print("Copilot initialized successfully!")
        result = await copilot.research(
            "Compare the GDP per capita of India, China, and Brazil over the last 10 years"
        )
        print("\n=== Analysis ===")
        print(result["analysis"])
        print("\n=== Metrics ===")
        print(json.dumps(result.get("metrics", {}), indent=2))
    asyncio.run(main())
