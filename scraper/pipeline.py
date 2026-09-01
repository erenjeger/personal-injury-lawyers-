import re

from models.attorney import Attorney

PI_TERMS = (
    "personal injury", "car accident", "truck accident", "motorcycle accident",
    "wrongful death", "premises liability", "slip and fall", "product liability",
    "pedestrian accident", "catastrophic injury", "injury lawyer", "injury attorney",
)

REQUIRED_FIELDS = ("name", "practice_area", "phone", "about")


def attorney_id(code, number):
    return f"{code}-{number:03d}"


def normalize_name(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def quality_check(raw):
    missing = [key for key in REQUIRED_FIELDS if not str(raw.get(key, "")).strip()]
    if missing:
        return False, f"missing required field(s): {', '.join(missing)}"

    practice = str(raw.get("practice_area", "")).lower()
    about = str(raw.get("about", "")).lower()
    if not any(term in f"{practice} {about}" for term in PI_TERMS):
        return False, "not clearly personal-injury related"

    if len(str(raw.get("about", "")).strip()) < 150:
        return False, "bio too short (minimum 150 characters)"

    return True, "ok"


def build_records(
    researcher,
    city,
    target=40,
    firm_limit=20,
    on_progress=None,
    min_confidence=0.45,
):
    firms = researcher.discover_firms(city["name"], city["state"], firm_limit)
    records, failures, seen_names, seen_urls = [], [], set(), set()

    if not firms:
        failures.append({
            "url": "",
            "reason": "no first-party law firms discovered",
            "name": "",
            "firm": "",
            "city": f"{city['name']}, {city['state']}",
            "search_engine": getattr(researcher, "search_engine_used", "") or "none",
            "search_error": getattr(researcher, "last_search_error", ""),
        })
        return records, failures

    for firm_index, firm in enumerate(firms, 1):
        if len(records) >= target:
            break

        pages = researcher.discover_attorney_pages(firm["url"])
        if not pages:
            failures.append({
                "url": firm["url"],
                "reason": "no likely attorney/profile pages discovered",
                "name": "",
                "firm": firm["name"],
            })
            continue

        accepted_from_firm = 0
        for page in pages:
            if len(records) >= target or accepted_from_firm >= 3:
                break
            if page in seen_urls:
                continue
            seen_urls.add(page)

            raw = researcher.extract_profile(
                page, city["name"], city["state"], firm["name"]
            )
            if not raw:
                failures.append({
                    "url": page,
                    "reason": "page fetch/extraction failed",
                    "name": "",
                    "firm": firm["name"],
                })
                continue

            key = normalize_name(raw.get("name", ""))
            if not key:
                failures.append({
                    "url": page,
                    "reason": "name not detected",
                    "name": "",
                    "firm": firm["name"],
                })
                continue
            if key in seen_names:
                continue

            ok, reason = quality_check(raw)
            if not ok:
                failures.append({
                    "url": page,
                    "reason": reason,
                    "name": raw.get("name", ""),
                    "firm": firm["name"],
                })
                continue

            confidence_value = float(raw.get("confidence", 0) or 0)
            if confidence_value < min_confidence:
                failures.append({
                    "url": page,
                    "reason": f"confidence below threshold: {confidence_value:.2f}",
                    "name": raw.get("name", ""),
                    "firm": firm["name"],
                })
                continue

            n = len(records) + 1
            raw.update({
                "attorney_id": attorney_id(city["code"], n),
                "menu_order": n,
                "status": "publish",
                "photo": "",
                "callout_text": "",
            })

            try:
                record = Attorney(**raw)
            except Exception as exc:
                failures.append({
                    "url": page,
                    "reason": f"validation: {exc}",
                    "name": raw.get("name", ""),
                    "firm": firm["name"],
                })
                continue

            records.append(record.model_dump())
            seen_names.add(key)
            accepted_from_firm += 1
            if on_progress:
                on_progress(len(records), target, firm_index, len(firms))

    if records and on_progress:
        on_progress(len(records), target, len(firms), len(firms))

    return records, failures
