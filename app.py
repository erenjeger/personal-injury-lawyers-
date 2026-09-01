from pathlib import Path
import pandas as pd
import streamlit as st
import yaml

from scraper.core import WebResearcher
from scraper.pipeline import build_records
from exporters.output import write_excel, write_csv, download_photos, zip_photos

BASE = Path(__file__).parent
OUT = BASE / "output"
OUT.mkdir(exist_ok=True)

st.set_page_config(page_title="Attorney Research Automation", page_icon="⚖️", layout="wide")
st.title("⚖️ Attorney Data Research Automation")
st.caption("First-party law-firm research assistant for personal-injury attorney profiles")

cities = yaml.safe_load((BASE / "config" / "cities.yaml").read_text())["cities"]

with st.sidebar:
    st.header("Research settings")
    selected_names = st.multiselect(
        "Cities",
        [f"{c['name']}, {c['state']}" for c in cities],
        default=["Phoenix, AZ"],
    )
    target = st.number_input("Attorneys per city", min_value=1, max_value=40, value=5)
    firms = st.number_input("Firms per city", min_value=1, max_value=20, value=5)
    delay = st.slider("Request delay (seconds)", min_value=0.5, max_value=5.0, value=1.5, step=0.5)
    confidence = st.slider("Minimum confidence", min_value=0.0, max_value=1.0, value=0.45, step=0.05)
    strict_robots = st.checkbox("Strict robots.txt", value=False, help="If enabled, an unavailable robots.txt is treated as not allowed.")
    run = st.button("🚀 Start research", type="primary", use_container_width=True)

if "records" not in st.session_state:
    st.session_state.records = []
if "failures" not in st.session_state:
    st.session_state.failures = []
if "stats" not in st.session_state:
    st.session_state.stats = {}

if run:
    if not selected_names:
        st.error("Select at least one city.")
        st.stop()

    selected = [c for c in cities if f"{c['name']}, {c['state']}" in selected_names]
    researcher = WebResearcher(delay=delay, strict_robots=strict_robots)
    all_records, all_failures = [], []
    progress = st.progress(0)
    status = st.empty()

    for city_index, city in enumerate(selected):
        status.info(f"Researching {city['name']}, {city['state']}…")

        def cb(done, total, firm_index, firm_total):
            city_fraction = min(done / max(total, 1), 1.0)
            overall = (city_index + city_fraction) / len(selected)
            progress.progress(min(overall, 1.0))
            status.info(f"{city['name']}: {done}/{total} attorneys | firm {firm_index}/{firm_total}")

        records, failures = build_records(
            researcher,
            city,
            target=target,
            firm_limit=firms,
            on_progress=cb,
            min_confidence=confidence,
        )
        all_records.extend(records)
        all_failures.extend(failures)

    st.session_state.records = all_records
    st.session_state.failures = all_failures
    st.session_state.stats = dict(researcher.stats)
    progress.progress(1.0)

    if all_records:
        status.success(f"Finished: {len(all_records)} valid profiles. {len(all_failures)} records skipped.")
    else:
        status.error("No valid profiles were found. Open the Diagnostics section below to see whether search, robots.txt, or profile validation stopped the run.")

records = st.session_state.records
failures = st.session_state.failures

if records:
    st.subheader("Results")
    df = pd.DataFrame(records)
    st.dataframe(df, use_container_width=True, hide_index=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Profiles", len(records))
    c2.metric("Cities", df["city"].nunique())
    c3.metric("Firms", df["firm"].nunique())
    c4.metric("Avg confidence", f"{df['confidence'].mean():.0%}" if "confidence" in df else "-")

    selected = [c for c in cities if c["name"] in df["city"].str.rsplit(", ", n=1).str[0].unique()]
    write_excel(records, selected, OUT / "attorney_research.xlsx")
    write_csv(records, OUT / "attorney_research.csv")
    download_photos(records, OUT / "photos")
    zip_photos(OUT / "photos", OUT / "photos.zip")
    pd.DataFrame(failures).to_csv(OUT / "failed_records.csv", index=False)

    st.download_button("⬇️ Download Excel", (OUT / "attorney_research.xlsx").read_bytes(), "attorney_research.xlsx")
    st.download_button("⬇️ Download CSV", (OUT / "attorney_research.csv").read_bytes(), "attorney_research.csv")
    st.download_button("⬇️ Download photos ZIP", (OUT / "photos.zip").read_bytes(), "photos.zip")

if failures:
    with st.expander(f"⚠️ Validation / extraction issues ({len(failures)})"):
        st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)

with st.expander("🔎 Diagnostics", expanded=not bool(records)):
    stats = st.session_state.stats
    if stats:
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Search requests", stats.get("search_requests", 0))
        d2.metric("Pages fetched", stats.get("pages_fetched", 0))
        d3.metric("Robots blocked", stats.get("blocked_robots", 0))
        d4.metric("Failed requests", stats.get("failed_requests", 0))
        if stats.get("search_requests", 0) and stats.get("pages_fetched", 0) == 0:
            st.warning("Search/discovery produced no fetchable first-party pages. This usually indicates a search-engine response/block or robots policy issue, not an Excel/export problem.")
    else:
        st.info("Run a small Phoenix test first. Diagnostics will appear here after the run.")

    if st.session_state.get("records") == [] and st.session_state.get("failures") == []:
        st.caption("Recommended smoke test: Phoenix → 2 attorneys → 2 firms → 0.5–1.0s delay.")
else:
    st.info("Select a city and start a research run. For quality control, begin with Phoenix and a small target batch.")
