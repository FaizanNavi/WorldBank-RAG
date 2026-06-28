import aiohttp
import asyncio
import time
import logging
from typing import List, Dict, Any, Optional
from ..cache.cache_manager import CacheManager
from ..utils.config import WB_BASE_URL, WB_RATE_LIMIT, REDIS_HOST, REDIS_PORT, REDIS_TTL
logger = logging.getLogger(__name__)
class WorldBankAPI:
    def __init__(self):
        self.base_url = WB_BASE_URL
        self.cache = CacheManager(host=REDIS_HOST, port=REDIS_PORT, ttl=REDIS_TTL)
        self._request_times = []
        self._rate_limit = WB_RATE_LIMIT
        self._latency_log = []
    async def _rate_limit_check(self):
        now = time.time()
        self._request_times = [t for t in self._request_times if now - t < 1.0]
        if len(self._request_times) >= self._rate_limit:
            wait_time = 1.0 - (now - self._request_times[0])
            if wait_time > 0:
                logger.debug(f"Rate limit: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
        self._request_times.append(time.time())
    async def fetch_indicator(
        self,
        country_code: str,
        indicator_code: str,
        start_year: int = 2010,
        end_year: int = 2024
    ) -> Dict[str, Any]:
        cache_params = {
            "country": country_code,
            "indicator": indicator_code,
            "start": start_year,
            "end": end_year
        }
        cached = self.cache.get("indicator", cache_params)
        if cached:
            return cached
        await self._rate_limit_check()
        url = f"{self.base_url}/country/{country_code}/indicator/{indicator_code}"
        params = {
            "format": "json",
            "date": f"{start_year}:{end_year}",
            "per_page": 100
        }
        start_time = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    latency = time.time() - start_time
                    self._latency_log.append(latency)
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list) and len(data) > 1 and data[1]:
                            clean_data = []
                            for item in data[1]:
                                if item.get("value") is not None:
                                    clean_data.append({
                                        "year": item["date"],
                                        "value": item["value"],
                                        "country": item["country"]["value"],
                                        "indicator": item["indicator"]["value"]
                                    })
                            result = {
                                "country": country_code,
                                "country_name": data[1][0]["country"]["value"] if data[1] else country_code,
                                "indicator": indicator_code,
                                "indicator_name": data[1][0]["indicator"]["value"] if data[1] else indicator_code,
                                "data": clean_data,
                                "total_records": len(clean_data),
                                "latency_ms": round(latency * 1000, 1)
                            }
                            self.cache.set("indicator", cache_params, result)
                            return result
                        else:
                            return {"error": f"No data found for {country_code}/{indicator_code}", "data": []}
                    else:
                        return {"error": f"API returned status {response.status}", "data": []}
        except asyncio.TimeoutError:
            return {"error": "Request timed out (15s limit)", "data": []}
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return {"error": str(e), "data": []}
    async def compare_countries(
        self,
        country_codes: List[str],
        indicator_code: str,
        start_year: int = 2010,
        end_year: int = 2024
    ) -> Dict[str, Any]:
        start_time = time.time()
        tasks = [
            self.fetch_indicator(cc, indicator_code, start_year, end_year)
            for cc in country_codes
        ]
        results = await asyncio.gather(*tasks)
        total_latency = time.time() - start_time
        individual_latencies = [r.get("latency_ms", 0) for r in results if isinstance(r, dict)]
        sequential_estimate = sum(individual_latencies)
        return {
            "comparison": list(results),
            "indicator": indicator_code,
            "countries_compared": country_codes,
            "parallel_latency_ms": round(total_latency * 1000, 1),
            "sequential_estimate_ms": round(sequential_estimate, 1),
            "speedup_percent": round(
                (1 - total_latency * 1000 / max(sequential_estimate, 1)) * 100, 1
            ) if sequential_estimate > 0 else 0
        }
    async def search_indicators(self, query: str) -> List[Dict]:
        url = f"{self.base_url}/indicator"
        params = {"format": "json", "per_page": 20, "q": query}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list) and len(data) > 1 and data[1]:
                            return [
                                {"id": ind["id"], "name": ind["name"], "source": ind.get("source", {}).get("value", "")}
                                for ind in data[1][:10]
                            ]
        except Exception as e:
            logger.error(f"Indicator search error: {e}")
        return []
    def get_metrics(self) -> Dict:
        cache_stats = self.cache.get_stats()
        if self._latency_log:
            sorted_latencies = sorted(self._latency_log)
            p50_idx = len(sorted_latencies) // 2
            p95_idx = int(len(sorted_latencies) * 0.95)
            p50 = round(sorted_latencies[p50_idx] * 1000, 1)
            p95 = round(sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)] * 1000, 1)
        else:
            p50 = 0
            p95 = 0
        return {
            "cache": cache_stats,
            "latency": {
                "p50_ms": p50,
                "p95_ms": p95,
                "total_requests": len(self._latency_log)
            }
        }
if __name__ == "__main__":
    async def main():
        wb = WorldBankAPI()
        print("=== Single Country Fetch ===")
        result = await wb.fetch_indicator("IN", "NY.GDP.PCAP.CD")
        print(f"India GDP per capita: {len(result.get('data', []))} data points")
        print("\n=== Parallel Country Comparison ===")
        comparison = await wb.compare_countries(["IN", "CN", "US", "BR", "DE"], "NY.GDP.PCAP.CD")
        print(f"Parallel: {comparison['parallel_latency_ms']}ms")
        print(f"Sequential estimate: {comparison['sequential_estimate_ms']}ms")
        print(f"Speedup: {comparison['speedup_percent']}%")
        print("\n=== Cache Stats ===")
        print(wb.get_metrics())
    asyncio.run(main())
