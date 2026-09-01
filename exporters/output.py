from copy import copy
from pathlib import Path
import io
import zipfile

import pandas as pd
import requests
from PIL import Image

# Exact column order from attorney-data-example.xlsx.
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
        row["photo"] = ""
        row["callout_text"] = ""
        row["status"] = "publish"
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def _style_sheet(ws):
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 24
    for cell in ws[1]:
        font = copy(cell.font)
        font.bold = True
        cell.font = font
    widths = {
        "A": 14, "B": 28, "C": 42, "D": 32, "E": 20, "F": 8,
        "G": 22, "H": 48, "I": 48, "J": 36, "K": 12, "L": 18,
        "M": 10, "N": 14, "O": 20, "P": 24, "Q": 90, "R": 18,
        "S": 12, "T": 14,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2):
        alignment = copy(row[16].alignment)
        alignment.wrap_text = True
        alignment.vertical = "top"
        row[16].alignment = alignment
        ws.row_dimensions[row[0].row].height = 72


def write_excel(records, cities, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for city in cities:
            city_records = [
                r for r in records
                if r.get("city", "").startswith(city["name"])
            ]
            df = to_frame(city_records)
            sheet = city["code"][:31]
            df.to_excel(writer, sheet_name=sheet, index=False)
            _style_sheet(writer.book[sheet])


def write_csv(records, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    to_frame(records).to_csv(path, index=False, encoding="utf-8-sig")


def _image_extension(image, response):
    content_type = response.headers.get("content-type", "").lower()
    if "png" in content_type or image.format == "PNG":
        return ".png"
    return ".jpg"


def download_photos(records, folder, timeout=20):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    session = requests.Session()
    session.headers.update({"User-Agent": "AttorneyResearchTool/3.0"})
    for r in records:
        url = r.get("photo_url", "")
        aid = r.get("attorney_id", "")
        if not url or not aid:
            results.append((aid, "missing", "No photo URL found"))
            continue
        try:
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            image = Image.open(io.BytesIO(resp.content))
            ext = _image_extension(image, resp)
            if ext == ".png":
                image = image.convert("RGBA") if image.mode != "RGBA" else image
                out = folder / f"{aid}.png"
                image.save(out, "PNG", optimize=True)
            else:
                image = image.convert("RGB")
                out = folder / f"{aid}.jpg"
                image.save(out, "JPEG", quality=92, optimize=True)
            r["photo"] = ""
            results.append((aid, "ok", str(out)))
        except Exception as exc:
            results.append((aid, "failed", str(exc)))
    return results


def zip_photos(folder, zip_path):
    folder, zip_path = Path(folder), Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                zf.write(p, arcname=p.name)
