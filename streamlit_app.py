import streamlit as st
import requests

st.set_page_config(page_title="WorldBank Research Copilot", page_icon="🌍", layout="wide")

st.title("🌍 WorldBank Research Copilot")
st.markdown("Ask natural language questions about global economic data — powered by **Groq + World Bank API**.")

BACKEND = "http://127.0.0.1:8002"

# Sidebar for comparison tool
with st.sidebar:
    st.header("⚡ Parallel Country Comparison")
    st.markdown("Compare N countries simultaneously using `asyncio.gather()`")
    countries_input = st.text_input("Country codes (comma separated)", value="IN,CN,US,BR,DE")
    indicator_input = st.text_input("Indicator code", value="NY.GDP.PCAP.CD")
    start_year = st.number_input("Start year", value=2010, min_value=1960, max_value=2024)
    end_year = st.number_input("End year", value=2023, min_value=1960, max_value=2024)
    if st.button("🚀 Run Comparison", use_container_width=True):
        codes = [c.strip().upper() for c in countries_input.split(",") if c.strip()]
        with st.spinner("Firing parallel API requests..."):
            try:
                res = requests.post(
                    f"{BACKEND}/compare",
                    json={"countries": codes, "indicator": indicator_input,
                          "start_year": int(start_year), "end_year": int(end_year)},
                    timeout=30
                )
                if res.status_code == 200:
                    data = res.json()
                    st.success(f"✅ Done! Parallel: {data.get('parallel_latency_ms')}ms | "
                               f"Sequential estimate: {data.get('sequential_estimate_ms')}ms | "
                               f"Speedup: **{data.get('speedup_percent')}%**")
                    for country_data in data.get("comparison", []):
                        if country_data.get("data"):
                            st.write(f"**{country_data.get('country_name', country_data['country'])}**: "
                                     f"{len(country_data['data'])} data points")
                else:
                    st.error(f"Error: {res.text}")
            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to backend. Is `uvicorn app.main:app --port 8002` running?")

    st.divider()
    st.header("🔍 Search Indicators")
    q = st.text_input("Search indicator name", value="GDP")
    if st.button("Search", use_container_width=True):
        try:
            res = requests.get(f"{BACKEND}/indicators/search", params={"q": q}, timeout=10)
            if res.status_code == 200:
                results = res.json().get("results", [])
                for r in results:
                    st.code(f"{r['id']}: {r['name']}")
        except Exception as e:
            st.error(str(e))

# Main chat area
st.divider()
st.subheader("💬 Research Chat")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask about global development data..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    try:
        with st.spinner("Fetching real data from World Bank API..."):
            res = requests.post(f"{BACKEND}/research", json={"question": prompt}, timeout=60)

        if res.status_code == 200:
            data = res.json()
            analysis = data.get("analysis", "No analysis generated.")
            metrics = data.get("metrics", {})

            with st.chat_message("assistant"):
                st.markdown(analysis)
                with st.expander("📊 Performance Metrics"):
                    cache = metrics.get("cache", {})
                    latency = metrics.get("latency", {})
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Cache Hit Rate", f"{cache.get('hit_rate_percent', 0):.1f}%")
                    col2.metric("P50 Latency", f"{latency.get('p50_ms', 0)}ms")
                    col3.metric("Total Requests", latency.get("total_requests", 0))

            st.session_state.messages.append({"role": "assistant", "content": analysis})
        else:
            st.error(f"Backend error {res.status_code}: {res.text}")

    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to backend. Is `uvicorn app.main:app --port 8002` running?")
    except Exception as e:
        st.error(f"Error: {e}")
