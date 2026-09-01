from pathlib import Path
import zipfile
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

cities = yaml.safe_load((BASE / "config" / "cities.yaml").read_text())['cities']

with st.sidebar:
    st.header("Research settings")
    selected_names = st.multiselect("Cities", [f"{c['name']}, {c['state']}" for c in cities], default=["Phoenix, AZ"])
    target = st.number_input("Attorneys per city", min_value=1, max_value=40, value=5)
    firms = st.number_input("Firms per city", min_value=1, max_value=20, value=5)
    delay = st.slider("Request delay (seconds)", min_value=1.0, max_value=5.0, value=1.5, step=0.5)
    run = st.button("🚀 Start research", type="primary", use_container_width=True)

if "records" not in st.session_state:
    st.session_state.records = []
if "failures" not in st.session_state:
    st.session_state.failures = []

if run:
    selected = [c for c in cities if f"{c['name']}, {c['state']}" in selected_names]
    researcher = WebResearcher(delay=delay)
    all_records, all_failures = [], []
    progress = st.progress(0)
    status = st.empty()
    for city in selected:
        status.info(f"Researching {city['name']}, {city['state']}…")
        def cb(done, total, firm_index, firm_total):
            progress.progress(min(done / total, 1.0))
            status.info(f"{city['name']}: {done}/{total} attorneys | firm {firm_index}/{firm_total}")
        records, failures = build_records(researcher, city, target=target, firm_limit=firms, on_progress=cb)
        all_records.extend(records)
        all_failures.extend(failures)
    st.session_state.records = all_records
    st.session_state.failures = all_failures
    status.success(f"Finished: {len(all_records)} valid profiles. {len(all_failures)} records skipped.")

records = st.session_state.records
if records:
    st.subheader("Results")
    df = pd.DataFrame(records)
    st.dataframe(df, use_container_width=True, hide_index=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Profiles", len(records))
    c2.metric("Cities", df['city'].nunique())
    c3.metric("Firms", df['firm'].nunique())

    selected = [c for c in cities if c['name'] in df['city'].str.rsplit(', ', n=1).str[0].unique()]
    write_excel(records, selected, OUT / "attorney_research.xlsx")
    write_csv(records, OUT / "attorney_research.csv")
    photo_results = download_photos(records, OUT / "photos")
    zip_photos(OUT / "photos", OUT / "photos.zip")
    pd.DataFrame(st.session_state.failures).to_csv(OUT / "failed_records.csv", index=False)

    st.download_button("⬇️ Download Excel", (OUT / "attorney_research.xlsx").read_bytes(), "attorney_research.xlsx")
    st.download_button("⬇️ Download CSV", (OUT / "attorney_research.csv").read_bytes(), "attorney_research.csv")
    st.download_button("⬇️ Download photos ZIP", (OUT / "photos.zip").read_bytes(), "photos.zip")
    if st.session_state.failures:
        st.warning(f"Skipped {len(st.session_state.failures)} profile(s). See failed_records.csv for reasons.")
else:
    st.info("Select a city and start a research run. For quality control, begin with Phoenix and a small target batch.")
