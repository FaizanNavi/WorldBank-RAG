import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from .agents.copilot import WorldBankCopilot, wb_api
from .pipeline.ingest import DataPipeline
from .utils.config import HOST, PORT
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)
app = FastAPI(
    title="WorldBank Research Copilot",
    description="AI-powered global development data analysis with parallel tool calling",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
copilot = WorldBankCopilot()
class ResearchRequest(BaseModel):
    question: str = Field(..., description="Natural language question about global development data")
    class Config:
        json_schema_extra = {
            "example": {
                "question": "Compare the GDP per capita of India, China, and USA over the last 10 years"
            }
        }
class CompareRequest(BaseModel):
    countries: List[str] = Field(..., description="List of ISO country codes")
    indicator: str = Field(..., description="World Bank indicator code")
    start_year: Optional[int] = Field(2010, description="Start year")
    end_year: Optional[int] = Field(2024, description="End year")
    class Config:
        json_schema_extra = {
            "example": {
                "countries": ["IN", "CN", "US"],
                "indicator": "NY.GDP.PCAP.CD",
                "start_year": 2015,
                "end_year": 2024
            }
        }
@app.get("/health")
async def health():
    return {"status": "ok", "service": "worldbank-copilot"}
@app.post("/research")
async def research(request: ResearchRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    logger.info(f"Research query: {request.question}")
    result = await copilot.research(request.question)
    return result
@app.post("/compare")
async def compare_countries(request: CompareRequest):
    if len(request.countries) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 countries to compare")
    if len(request.countries) > 10:
        raise HTTPException(status_code=400, detail="Max 10 countries per comparison")
    logger.info(f"Compare: {request.countries} on {request.indicator}")
    result = await wb_api.compare_countries(
        request.countries, request.indicator, request.start_year, request.end_year
    )
    return result
@app.get("/metrics")
async def metrics():
    return wb_api.get_metrics()
@app.get("/indicators/search")
async def search_indicators(q: str):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")
    results = await wb_api.search_indicators(q)
    return {"query": q, "results": results}
@app.post("/pipeline/run")
async def run_pipeline(quick: bool = True):
    pipeline = DataPipeline()
    if quick:
        from .pipeline.ingest import POPULAR_INDICATORS, POPULAR_COUNTRIES
        quick_indicators = {k: v for k, v in list(POPULAR_INDICATORS.items())[:3]}
        quick_countries = POPULAR_COUNTRIES[:5]
        result = await pipeline.run(quick_indicators, quick_countries)
    else:
        result = await pipeline.run()
    return result
@app.get("/data/status")
async def data_status():
    pipeline = DataPipeline()
    return pipeline.get_available_data()
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
