# Attorney Research Automation Tool

Python/Streamlit tool for researching personal-injury attorneys from law-firm websites and exporting validated records to Excel/CSV with optional headshot downloads.

## Scope
- City-driven firm discovery
- Search-engine result parsing (DuckDuckGo HTML)
- First-party law-firm filtering
- Attorney/team/profile page discovery
- Structured extraction of name, practice areas, firm, phone, education, affiliations, languages, bio and related fields
- Required-field validation and duplicate detection
- Attorney ID generation (PHX-001, LAX-001, etc.)
- Headshot download and normalization
- Excel workbook with one sheet per city
- CSV export, ZIP photo export, and failed-record log
- Respectful crawling with rate limits and robots.txt checks

## Important
This is an automation/research assistant, not a guarantee of 440 correct records. Websites differ substantially. Always review a sample batch before publishing data. Only collect information that is publicly available and permitted by the target site's terms/robots policy.

## Run
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Default cities
Phoenix, Los Angeles, San Diego, San Francisco, Denver, Washington D.C., Jacksonville, Miami, Atlanta, Chicago, Baltimore.

## Output
`output/attorney_research.xlsx`, `output/attorney_research.csv`, `output/photos.zip`, and `output/failed_records.csv`.
