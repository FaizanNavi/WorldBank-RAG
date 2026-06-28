# 🧪 Testing Guide — WorldBank Research Copilot

## Prerequisites

```bash
pip install -r requirements.txt
cp .env.example .env
# Add your GROQ_API_KEY to .env
```

## Test 1: Unit Tests (No API key needed)

```bash
pytest tests/ -v
```

Expected output: All tests pass. These use mocked API responses.

## Test 2: World Bank API (No API key needed)

The WB API is free and requires no authentication:

```bash
python -c "
import asyncio
from app.tools.wb_api import WorldBankAPI

async def test():
    wb = WorldBankAPI()
    result = await wb.fetch_indicator('IN', 'NY.GDP.PCAP.CD')
    print(f'India GDP records: {len(result.get(\"data\", []))}')
    
    comparison = await wb.compare_countries(['IN', 'CN', 'US'], 'NY.GDP.PCAP.CD')
    print(f'Parallel latency: {comparison[\"parallel_latency_ms\"]}ms')
    print(f'Sequential estimate: {comparison[\"sequential_estimate_ms\"]}ms')
    print(f'Speedup: {comparison[\"speedup_percent\"]}%')

asyncio.run(test())
"
```

Expected: You should see ~60-80% speedup with parallel fetching.

## Test 3: Data Pipeline (No API key needed)

```bash
# Quick mode - fetches 3 indicators for 5 countries
python -m app.pipeline.ingest --quick
```

Expected output:
```
============================================================
  World Bank Data Pipeline
  3 indicators × 5 countries
============================================================

  📊 Fetching: GDP per capita (current US$) (NY.GDP.PCAP.CD)...
     ✅ 85 records saved, 15 skipped (3.2s)
  ...
  ✅ Pipeline complete!
```

Check the generated files:
```bash
# CSV files
ls data/csv/

# SQLite database
python -c "
import sqlite3
conn = sqlite3.connect('data/worldbank.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM indicators')
print(f'Total records: {cursor.fetchone()[0]}')
cursor.execute('SELECT COUNT(*) FROM pipeline_runs')
print(f'Pipeline runs: {cursor.fetchone()[0]}')
conn.close()
"
```

## Test 4: FastAPI Server (Needs GROQ_API_KEY)

```bash
# Start server
uvicorn app.main:app --reload --port 8002

# In another terminal:

# Health check
curl http://localhost:8002/health

# Research query
curl -X POST http://localhost:8002/research \
  -H "Content-Type: application/json" \
  -d '{"question": "What is India GDP per capita trend?"}'

# Parallel comparison
curl -X POST http://localhost:8002/compare \
  -H "Content-Type: application/json" \
  -d '{"countries": ["IN", "CN", "US", "BR", "DE"], "indicator": "NY.GDP.PCAP.CD"}'

# Check metrics
curl http://localhost:8002/metrics
```

## Test 5: Interactive API Docs

Open http://localhost:8002/docs in your browser — FastAPI generates interactive documentation automatically.

## What to Show in Interviews

1. **Parallel speedup**: Run the comparison and show the latency difference
2. **Cache hit rate**: Run the same query twice, show /metrics cache stats
3. **Data pipeline**: Run `--quick` and show the CSV + SQLite output
4. **Token budget**: Explain how tiktoken prevents context overflow
