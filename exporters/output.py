from pathlib import Path
import io
import zipfile

import pandas as pd
import requests
from PIL import Image

COLUMNS = [
    "attorney_id", "name", "practice_area", "firm", "city", "state",
    "licensed_states", "education", "affiliations", "badges", "photo",
    "years_experience", "rating", "review_count", "phone", "languages",
    "about", "callout_text", "status", "menu_order"
]


def to_frame(records):
    rows = []
    for r in records:
        row = {k: r.get(k, "") for k in COLUMNS}
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def write_excel(records, cities, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for city in cities:
            city_records = [r for r in records if r.get("city", "").startswith(city["name"])]
            df = to_frame(city_records)
            sheet = city["code"][:31]
            df.to_excel(writer, sheet_name=sheet, index=False)
            ws = writer.book[sheet]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 2, 12), 55)


def write_csv(records, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    to_frame(records).to_csv(path, index=False, encoding="utf-8-sig")


def download_photos(records, folder, timeout=20):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for r in records:
        url = r.get("photo_url", "")
        aid = r.get("attorney_id", "")
        if not url or not aid:
            continue
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": "AttorneyResearchTool/1.0"})
            resp.raise_for_status()
            image = Image.open(io.BytesIO(resp.content)).convert("RGB")
            out = folder / f"{aid}.jpg"
            image.save(out, "JPEG", quality=92)
            r["photo"] = out.name
            results.append((aid, "ok", str(out)))
        except Exception as exc:
            results.append((aid, "failed", str(exc)))
    return results


def zip_photos(folder, zip_path):
    folder, zip_path = Path(folder), Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in folder.glob("*.jpg"):
            zf.write(p, arcname=p.name)
