import re
from collections import defaultdict

from models.attorney import Attorney


def attorney_id(code, number):
    return f"{code}-{number:03d}"


def build_records(researcher, city, target=40, firm_limit=20, on_progress=None):
    firms = researcher.discover_firms(city["name"], city["state"], firm_limit)
    records = []
    seen_names = set()
    failures = []
    for firm_index, firm in enumerate(firms, 1):
        if len(records) >= target:
            break
        pages = researcher.discover_attorney_pages(firm["url"])
        for page in pages:
            if len(records) >= target:
                break
            raw = researcher.extract_profile(page, city["name"], city["state"], firm["name"])
            if not raw:
                continue
            key = re.sub(r"[^a-z0-9]", "", raw.get("name", "").lower())
            if not key or key in seen_names:
                continue
            if not all(raw.get(k, "").strip() for k in ("name", "practice_area", "phone", "about")):
                failures.append({"url": page, "reason": "missing required field", "name": raw.get("name", "")})
                continue
            # The source requirement is specifically personal injury; avoid unrelated team profiles.
            combined = (raw.get("practice_area", "") + " " + raw.get("about", "")).lower()
            if "personal injury" not in combined and "personal-injury" not in combined:
                continue
            seen_names.add(key)
            n = len(records) + 1
            raw["attorney_id"] = attorney_id(city["code"], n)
            raw["menu_order"] = n
            raw["status"] = "publish"
            try:
                record = Attorney(**raw)
            except Exception as exc:
                failures.append({"url": page, "reason": f"validation: {exc}", "name": raw.get("name", "")})
                continue
            records.append(record.model_dump())
            if on_progress:
                on_progress(len(records), target, firm_index, len(firms))
    return records, failures
