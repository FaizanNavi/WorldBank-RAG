"""
WorldBank Research Copilot — Developer Dashboard (Streamlit)
────────────────────────────────────────────────────────────
Internal tool: metrics, parallel compare, pipeline, indicator search.
Run with:  uv run streamlit run streamlit_app.py
"""

import streamlit as st
import requests
import json
from datetime import datetime

# ──────────────────────── CONFIG ────────────────────────
BACKEND = "http://127.0.0.1:8002"

st.set_page_config(
    page_title="WB Copilot · Dev Dashboard",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────── HELPERS ────────────────────────
def get(path: str, **kwargs):
    return requests.get(f"{BACKEND}{path}", timeout=15, **kwargs)

def post(path: str, **kwargs):
    return requests.post(f"{BACKEND}{path}", timeout=60, **kwargs)

def backend_ok() -> bool:
    try:
        return get("/health").status_code == 200
    except Exception:
        return False

# ──────────────────────── SIDEBAR ────────────────────────
with st.sidebar:
    st.markdown("## 🌍 WorldBank Copilot")
    st.caption("Developer Dashboard · Internal use only")
    st.divider()

    alive = backend_ok()
    if alive:
        st.success("✅ Backend connected — `localhost:8002`")
    else:
        st.error("❌ Backend offline")
        st.code("uv run uvicorn app.main:app --port 8002 --reload", language="bash")

    st.divider()

    # ── Parallel Country Compare ──
    st.subheader("⚡ Parallel Country Compare")
    st.caption("Fires all requests via `asyncio.gather()` — typically 60-80% faster than sequential.")
    cmp_countries = st.text_input("Country codes (comma-separated)", value="IN,CN,US,BR,DE", key="cmp_c")
    cmp_indicator = st.text_input("Indicator code", value="NY.GDP.PCAP.CD", key="cmp_i")
    col1, col2 = st.columns(2)
    cmp_start = col1.number_input("Start year", value=2010, min_value=1960, max_value=2024)
    cmp_end   = col2.number_input("End year",   value=2023, min_value=1960, max_value=2024)

    if st.button("🚀 Run Parallel Compare", use_container_width=True, type="primary"):
        codes = [c.strip().upper() for c in cmp_countries.split(",") if c.strip()]
        with st.spinner(f"Fetching {len(codes)} countries in parallel…"):
            try:
                r = post("/compare", json={
                    "countries": codes,
                    "indicator": cmp_indicator,
                    "start_year": int(cmp_start),
                    "end_year":   int(cmp_end),
                })
                if r.status_code == 200:
                    d = r.json()
                    st.success(
                        f"Parallel: **{d.get('parallel_latency_ms')}ms** | "
                        f"Sequential est: {d.get('sequential_estimate_ms')}ms | "
                        f"Speedup: **{d.get('speedup_percent')}%** 🚀"
                    )
                    for c in d.get("comparison", []):
                        if c.get("data"):
                            latest = c["data"][0]
                            st.markdown(
                                f"**{c.get('country_name', c['country'])}** ({c['country']}) — "
                                f"{len(c['data'])} pts · latest {latest['year']}: `{float(latest['value']):,.1f}`"
                            )
                else:
                    st.error(f"HTTP {r.status_code}: {r.text}")
            except requests.exceptions.ConnectionError:
                st.error("Cannot reach backend.")

    st.divider()

    # ── Indicator Search ──
    st.subheader("🔍 Indicator Search")
    q = st.text_input("Search indicator name", value="GDP", key="isearch")
    if st.button("Search", use_container_width=True):
        try:
            r = get("/indicators/search", params={"q": q})
            for item in r.json().get("results", []):
                st.code(f"{item['id']}  {item['name']}")
        except Exception as e:
            st.error(str(e))


# ──────────────────────── TABS ────────────────────────
tab_chat, tab_metrics, tab_pipeline = st.tabs(["💬 Research Chat", "📊 Live Metrics", "⚡ Data Pipeline"])


# ════════════════════════ TAB: CHAT ════════════════════════
with tab_chat:
    st.subheader("Research Chat")
    st.caption("AI-powered natural language queries against live World Bank data.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # render history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("metrics"):
                m = msg["metrics"]
                c, l = m.get("cache", {}), m.get("latency", {})
                with st.expander("📊 Request metrics"):
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    mc1.metric("Cache hit rate", f"{c.get('hit_rate_percent', 0):.1f}%")
                    mc2.metric("P50 latency",    f"{l.get('p50_ms', 0)} ms")
                    mc3.metric("P95 latency",    f"{l.get('p95_ms', 0)} ms")
                    mc4.metric("Backend",        c.get("backend", "—"))

    if prompt := st.chat_input("Ask about global development data…"):
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.spinner("Querying World Bank API + AI analysis…"):
            try:
                r = post("/research", json={"question": prompt})
                if r.status_code == 200:
                    d = r.json()
                    analysis = d.get("analysis", "No analysis returned.")
                    metrics  = d.get("metrics", {})

                    with st.chat_message("assistant"):
                        st.markdown(analysis)
                        c, l = metrics.get("cache", {}), metrics.get("latency", {})
                        with st.expander("📊 Request metrics"):
                            mc1, mc2, mc3, mc4 = st.columns(4)
                            mc1.metric("Cache hit rate", f"{c.get('hit_rate_percent', 0):.1f}%")
                            mc2.metric("P50 latency",    f"{l.get('p50_ms', 0)} ms")
                            mc3.metric("P95 latency",    f"{l.get('p95_ms', 0)} ms")
                            mc4.metric("Backend",        c.get("backend", "—"))

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": analysis,
                        "metrics": metrics,
                    })
                else:
                    st.error(f"Backend error {r.status_code}: {r.text}")
            except requests.exceptions.ConnectionError:
                st.error("Cannot reach backend. Start it first.")
            except Exception as e:
                st.error(str(e))


# ════════════════════════ TAB: METRICS ════════════════════════
with tab_metrics:
    st.subheader("Live Performance Metrics")
    st.caption("Real-time cache and latency data from the FastAPI backend `/metrics` endpoint.")

    col_r, _ = st.columns([1, 5])
    refresh = col_r.button("🔄 Refresh", key="refresh_metrics")

    try:
        r = get("/metrics")
        d = r.json()
        cache   = d.get("cache", {})
        latency = d.get("latency", {})

        st.markdown("#### Cache")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Hits",         cache.get("hits", 0))
        c2.metric("Misses",       cache.get("misses", 0))
        c3.metric("Hit Rate",     f"{cache.get('hit_rate_percent', 0):.1f}%")
        c4.metric("Backend",      cache.get("backend", "—"))

        st.markdown("#### Latency")
        l1, l2, l3 = st.columns(3)
        l1.metric("P50",             f"{latency.get('p50_ms', 0)} ms")
        l2.metric("P95",             f"{latency.get('p95_ms', 0)} ms")
        l3.metric("Total Requests",  latency.get("total_requests", 0))

        st.divider()
        with st.expander("Raw JSON response"):
            st.json(d)

    except Exception as e:
        st.error(f"Cannot load metrics: {e}")
        st.code("uv run uvicorn app.main:app --port 8002 --reload")


# ════════════════════════ TAB: PIPELINE ════════════════════════
with tab_pipeline:
    st.subheader("Data Ingestion Pipeline")
    st.caption("Pattern: World Bank JSON → Normalize → CSV → SQLite with audit logging.")

    st.markdown(
        """
        | Mode | Indicators | Countries | Est. time |
        |------|-----------|-----------|-----------|
        | Quick | 3 | 5 | ~30 s |
        | Full  | 10 | 20 | ~3 min |
        """
    )

    p1, p2, p3 = st.columns(3)
    run_quick = p1.button("🚀 Quick Run",   type="primary")
    run_full  = p2.button("📦 Full Run")
    run_status= p3.button("📋 Data Status")

    if run_quick or run_full:
        quick = run_quick
        with st.spinner(f"Running {'quick' if quick else 'full'} pipeline… this may take a while"):
            try:
                r = post(f"/pipeline/run?quick={str(quick).lower()}")
                if r.status_code == 200:
                    d = r.json()
                    st.success(
                        f"✅ Pipeline complete — {d.get('total_records', 0)} records in "
                        f"{d.get('total_duration_seconds', '?')}s · DB: `{d.get('database', '?')}`"
                    )
                    if d.get("indicators"):
                        rows = []
                        for code, info in d["indicators"].items():
                            rows.append({
                                "Indicator": info.get("name", code),
                                "Code": code,
                                "Inserted": info.get("db_inserted", 0),
                                "Duration (s)": info.get("duration_seconds", "?"),
                            })
                        st.dataframe(rows, use_container_width=True)
                else:
                    st.error(f"HTTP {r.status_code}: {r.text}")
            except Exception as e:
                st.error(str(e))

    if run_status:
        try:
            r = get("/data/status")
            d = r.json()
            indicators = d.get("indicators", [])
            if indicators:
                st.dataframe(indicators, use_container_width=True)
            else:
                st.info("No data yet. Run the pipeline first.")
        except Exception as e:
            st.error(str(e))

    st.divider()
    with st.expander("ℹ️ API Endpoints"):
        st.markdown("""
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/research` | Natural language → AI analysis |
| `POST` | `/compare` | Parallel multi-country fetch |
| `GET`  | `/metrics` | Cache & latency stats |
| `GET`  | `/indicators/search?q=...` | Search indicator codes |
| `GET`  | `/data/status` | Local DB contents |
| `POST` | `/pipeline/run` | Trigger ingestion |
| `GET`  | `/health` | Health check |
""")
