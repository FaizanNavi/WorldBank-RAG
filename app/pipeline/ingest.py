import os
import sys
import csv
import json
import sqlite3
import aiohttp
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..utils.config import WB_BASE_URL

# Ensure UTF-8 output even on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent.parent.parent / "data"
CSV_DIR = DATA_DIR / "csv"
RAW_DIR = DATA_DIR / "raw_json"
DB_PATH = DATA_DIR / "worldbank.db"
POPULAR_INDICATORS = {
    "NY.GDP.PCAP.CD": "GDP per capita (current US$)",
    "NY.GDP.MKTP.CD": "GDP (current US$)",
    "SP.POP.TOTL": "Population, total",
    "SP.DYN.LE00.IN": "Life expectancy at birth",
    "SE.ADT.LITR.ZS": "Literacy rate, adult total",
    "SL.UEM.TOTL.ZS": "Unemployment, total",
    "EN.ATM.CO2E.PC": "CO2 emissions (metric tons per capita)",
    "SI.POV.DDAY": "Poverty headcount ratio at $2.15/day",
    "FP.CPI.TOTL.ZG": "Inflation, consumer prices (annual %)",
    "BX.KLT.DINV.CD.WD": "Foreign direct investment, net inflows",
}
POPULAR_COUNTRIES = [
    "IN", "CN", "US", "BR", "DE", "JP", "GB", "FR", "NG", "ZA",
    "RU", "AU", "CA", "KR", "MX", "ID", "TR", "SA", "AR", "EG"
]
class DataPipeline:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._ensure_dirs()
        self._init_db()
        self._run_log = []
    def _ensure_dirs(self):
        CSV_DIR.mkdir(parents=True, exist_ok=True)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
    def _init_db(self):
        """Create tables, migrate missing columns, then create indexes — all in order."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # ── 1. Create tables with minimal guaranteed columns ──────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indicators (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                country_code TEXT    NOT NULL DEFAULT '',
                year         INTEGER NOT NULL DEFAULT 0,
                value        REAL    NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # ── 2. Migrate: add columns missing from older DB schemas ─────────
        _REQUIRED = {
            "indicators": [
                ("country_name",   "TEXT NOT NULL DEFAULT ''"),
                ("indicator_code", "TEXT NOT NULL DEFAULT ''"),
                ("indicator_name", "TEXT NOT NULL DEFAULT ''"),
                ("created_at",     "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ],
            "pipeline_runs": [
                ("indicator_code",   "TEXT NOT NULL DEFAULT ''"),
                ("countries_count",  "INTEGER"),
                ("records_inserted", "INTEGER"),
                ("records_skipped",  "INTEGER"),
                ("errors",           "TEXT"),
                ("duration_seconds", "REAL"),
            ],
        }
        for table, cols in _REQUIRED.items():
            cursor.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in cursor.fetchall()}
            for col_name, col_def in cols:
                if col_name not in existing:
                    cursor.execute(
                        f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"
                    )
                    logger.info(f"Migration: added '{col_name}' to table '{table}'")
        conn.commit()

        # ── 3. Create indexes (safe now that all columns exist) ───────────
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_indicator_country
                ON indicators(indicator_code, country_code)
            """)
            conn.commit()
        except sqlite3.OperationalError as exc:
            logger.warning(f"Index creation skipped: {exc}")

        conn.close()
        logger.info(f"Database ready at {self.db_path}")
    async def fetch_indicator_data(
        self,
        indicator_code: str,
        countries: List[str],
        start_year: int = 2000,
        end_year: int = 2024
    ) -> List[Dict]:
        all_records = []
        async with aiohttp.ClientSession() as session:
            for country in countries:
                url = f"{WB_BASE_URL}/country/{country}/indicator/{indicator_code}"
                params = {
                    "format": "json",
                    "date": f"{start_year}:{end_year}",
                    "per_page": 100,
                    "page": 1
                }
                try:
                    while True:
                        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            if resp.status != 200:
                                logger.warning(f"API error for {country}/{indicator_code}: HTTP {resp.status}")
                                self._run_log.append(f"ERROR: {country}/{indicator_code} - HTTP {resp.status}")
                                break
                            data = await resp.json()
                            if not isinstance(data, list) or len(data) < 2 or not data[1]:
                                break
                            metadata = data[0]
                            records = data[1]
                            all_records.extend(records)
                            current_page = metadata.get("page", 1)
                            total_pages = metadata.get("pages", 1)
                            if current_page >= total_pages:
                                break
                            params["page"] = current_page + 1
                    logger.info(f"Fetched {country}/{indicator_code}: got {len(all_records)} records so far")
                    await asyncio.sleep(0.1)
                except asyncio.TimeoutError:
                    logger.error(f"Timeout fetching {country}/{indicator_code}")
                    self._run_log.append(f"TIMEOUT: {country}/{indicator_code}")
                except Exception as e:
                    logger.error(f"Error fetching {country}/{indicator_code}: {e}")
                    self._run_log.append(f"ERROR: {country}/{indicator_code} - {str(e)}")
        raw_file = RAW_DIR / f"{indicator_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(raw_file, "w") as f:
            json.dump(all_records, f, indent=2)
        logger.info(f"Saved raw JSON: {raw_file} ({len(all_records)} records)")
        return all_records
    def normalize_to_csv(self, records: List[Dict], indicator_code: str) -> str:
        csv_path = CSV_DIR / f"{indicator_code}.csv"
        clean_rows = []
        skipped = 0
        for record in records:
            if record.get("value") is None:
                skipped += 1
                continue
            try:
                row = {
                    "country_code": record["country"]["id"],
                    "country_name": record["country"]["value"],
                    "indicator_code": record["indicator"]["id"],
                    "indicator_name": record["indicator"]["value"],
                    "year": int(record["date"]),
                    "value": float(record["value"])
                }
                clean_rows.append(row)
            except (KeyError, ValueError, TypeError) as e:
                skipped += 1
                logger.debug(f"Skipped malformed record: {e}")
        clean_rows.sort(key=lambda x: (x["country_code"], x["year"]))
        if clean_rows:
            fieldnames = ["country_code", "country_name", "indicator_code", "indicator_name", "year", "value"]
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(clean_rows)
        logger.info(f"CSV saved: {csv_path} ({len(clean_rows)} rows, {skipped} skipped)")
        return str(csv_path)
    def persist_to_db(self, records: List[Dict], indicator_code: str) -> Dict[str, int]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        inserted = 0
        skipped = 0
        for record in records:
            if record.get("value") is None:
                skipped += 1
                continue
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO indicators "
                    "(country_code, country_name, indicator_code, indicator_name, year, value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        record["country"]["id"],
                        record["country"]["value"],
                        record["indicator"]["id"],
                        record["indicator"]["value"],
                        int(record["date"]),
                        float(record["value"])
                    )
                )
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except (KeyError, ValueError, TypeError):
                skipped += 1
        conn.commit()
        conn.close()
        logger.info(f"DB persist: {inserted} inserted, {skipped} skipped for {indicator_code}")
        return {"inserted": inserted, "skipped": skipped}
    def _log_run(self, indicator_code: str, countries_count: int, inserted: int, skipped: int, duration: float):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pipeline_runs "
            "(indicator_code, countries_count, records_inserted, records_skipped, errors, duration_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (indicator_code, countries_count, inserted, skipped, json.dumps(self._run_log), round(duration, 2))
        )
        conn.commit()
        conn.close()
    async def run(
        self,
        indicators: Optional[Dict[str, str]] = None,
        countries: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        indicators = indicators or POPULAR_INDICATORS
        countries = countries or POPULAR_COUNTRIES
        results = {}
        total_start = datetime.now()
        logger.info(f"Pipeline starting: {len(indicators)} indicators x {len(countries)} countries")
        print(f"\n{'='*60}")
        print(f"  World Bank Data Pipeline")
        print(f"  {len(indicators)} indicators x {len(countries)} countries")
        print(f"  Started at: {total_start.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        for indicator_code, indicator_name in indicators.items():
            self._run_log = []
            start_time = datetime.now()
            print(f"  >> Fetching: {indicator_name} ({indicator_code})...")
            raw_records = await self.fetch_indicator_data(indicator_code, countries)
            csv_path = self.normalize_to_csv(raw_records, indicator_code)
            db_result = self.persist_to_db(raw_records, indicator_code)
            duration = (datetime.now() - start_time).total_seconds()
            self._log_run(indicator_code, len(countries), db_result["inserted"], db_result["skipped"], duration)
            results[indicator_code] = {
                "name": indicator_name,
                "raw_records": len(raw_records),
                "csv_path": csv_path,
                "db_inserted": db_result["inserted"],
                "db_skipped": db_result["skipped"],
                "duration_seconds": round(duration, 2),
                "errors": self._run_log
            }
            print(f"     [OK] {db_result['inserted']} records saved, {db_result['skipped']} skipped ({duration:.1f}s)")
        total_duration = (datetime.now() - total_start).total_seconds()
        total_records = sum(r["db_inserted"] for r in results.values())
        print(f"\n{'='*60}")
        print(f"  Pipeline complete!")
        print(f"  Total records: {total_records}")
        print(f"  Total time: {total_duration:.1f}s")
        print(f"  Database: {self.db_path}")
        print(f"{'='*60}\n")
        return {
            "status": "complete",
            "total_records": total_records,
            "total_duration_seconds": round(total_duration, 2),
            "indicators": results,
            "database": str(self.db_path),
            "csv_directory": str(CSV_DIR)
        }
    def query_local(self, indicator_code: str, country_code: str, start_year: int = 2000, end_year: int = 2024) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM indicators WHERE indicator_code=? AND country_code=? "
            "AND year>=? AND year<=? ORDER BY year",
            (indicator_code, country_code, start_year, end_year)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    def get_available_data(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT indicator_code, indicator_name,
                   COUNT(DISTINCT country_code) as countries,
                   COUNT(*) as records,
                   MIN(year) as min_year, MAX(year) as max_year
            FROM indicators
            GROUP BY indicator_code, indicator_name
            ORDER BY records DESC
        """)
        indicators = []
        for row in cursor.fetchall():
            indicators.append({
                "indicator_code": row[0],
                "indicator_name": row[1],
                "countries": row[2],
                "records": row[3],
                "year_range": f"{row[4]}-{row[5]}"
            })
        cursor.execute("""
            SELECT timestamp, indicator_code, records_inserted, duration_seconds
            FROM pipeline_runs
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        runs = []
        for row in cursor.fetchall():
            runs.append({
                "timestamp": row[0],
                "indicator": row[1],
                "records": row[2],
                "duration_s": row[3]
            })
        conn.close()
        return {"indicators": indicators, "recent_runs": runs}
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    quick = "--quick" in sys.argv
    pipeline = DataPipeline()
    if quick:
        quick_indicators = {k: v for k, v in list(POPULAR_INDICATORS.items())[:3]}
        quick_countries = POPULAR_COUNTRIES[:5]
        result = asyncio.run(pipeline.run(quick_indicators, quick_countries))
    else:
        result = asyncio.run(pipeline.run())
    print(f"\nPipeline finished. Database at: {result['database']}")
