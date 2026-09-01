import re
from urllib.parse import urlparse

DIRECTORY_DOMAINS = {
    "findlaw.com", "avvo.com", "justia.com", "superlawyers.com", "lawyers.com",
    "martindale.com", "martindale-hubbell.com", "yelp.com", "yellowpages.com",
    "lawinfo.com", "nolo.com", "lawtally.com", "freelawyer.com", "lawyer.com",
    "rocketlawyer.com", "legalmatch.com", "lawyers.findlaw.com",
}
SEARCH_DOMAINS = {
    "bing.com", "google.com", "duckduckgo.com", "yahoo.com", "search.brave.com",
}
NOISE_DOMAINS = {
    "thefreedictionary.com", "wikipedia.org", "facebook.com", "linkedin.com",
    "instagram.com", "youtube.com", "mapquest.com", "tripadvisor.com",
    "indeed.com", "glassdoor.com", "quizlet.com", "quizizz.com", "pinterest.com",
    "reddit.com", "amazon.com", "ebay.com", "crunchbase.com",
}
PI_TERMS = (
    "personal injury", "car accident", "truck accident", "motorcycle accident",
    "wrongful death", "premises liability", "slip and fall", "product liability",
    "pedestrian accident", "catastrophic injury", "injury lawyer", "injury attorney",
)
LEGAL_TERMS = (
    "law firm", "law office", "attorneys", "attorney at law", "lawyers",
    "practice areas", "our attorneys", "our lawyers", "meet our team", "free consultation",
    "personal injury", "injury attorney", "injury lawyer", "legal team",
)


def host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").split(":", 1)[0]


def blocked_domain(url: str) -> bool:
    h = host(url)
    return any(h == d or h.endswith("." + d) for d in DIRECTORY_DOMAINS | SEARCH_DOMAINS | NOISE_DOMAINS)


def candidate_score(title: str, url: str, city: str, state: str) -> int:
    text = f"{title} {url}".lower()
    score = 0
    if any(term in text for term in PI_TERMS):
        score += 4
    if any(term in text for term in ("law firm", "law office", "attorney", "attorneys", "lawyer", "lawyers")):
        score += 3
    if city.lower() in text:
        score += 2
    if state.lower() in text or state.lower().replace(".", "") in text:
        score += 1
    return score


def page_score(text: str, city: str, state: str) -> tuple[int, bool]:
    hay = text.lower()
    pi_hits = sum(1 for term in PI_TERMS if term in hay)
    legal_hits = sum(1 for term in LEGAL_TERMS if term in hay)
    city_hit = city.lower() in hay
    state_hit = state.lower() in hay or state.lower().replace(".", "") in hay
    score = min(pi_hits, 3) * 2 + min(legal_hits, 4) + int(city_hit) + int(state_hit)
    # A first-party firm homepage should have either explicit PI relevance,
    # or a strong legal-practice signal plus local signal.
    is_firm = (pi_hits >= 1 and legal_hits >= 1) or (legal_hits >= 3 and (city_hit or state_hit))
    return score, is_firm


def firm_name_from_title(title: str) -> str:
    value = re.sub(r"\s*[-|–—:•].*$", "", title or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value or "Unknown Law Firm"


def discover_firms_robust(researcher, city: str, state: str, limit: int = 20):
    """Discover first-party PI law firms without treating search-engine redirects as firms."""
    queries = [
        f'"{city}" "{state}" personal injury attorney',
        f'"{city}" "{state}" personal injury law firm',
        f'"{city}" personal injury lawyer',
        f'personal injury attorney "{city}"',
        f'personal injury lawyers "{city}"',
    ]
    candidates = {}
    for query in queries:
        for title, url in researcher.search(query, limit=40):
            if not url or blocked_domain(url):
                continue
            h = host(url)
            if not h:
                continue
            score = candidate_score(title, url, city, state)
            if score < 4:
                continue
            current = candidates.get(h)
            if current is None or score > current["score"]:
                candidates[h] = {"name": firm_name_from_title(title), "url": url, "domain": h, "score": score}

    ranked = sorted(candidates.values(), key=lambda item: item["score"], reverse=True)
    firms = []
    for candidate in ranked:
        response = researcher.get(candidate["url"])
        if not response:
            continue
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else candidate["name"]
            visible = soup.get_text(" ", strip=True)
            score, is_firm = page_score(f"{title} {visible[:30000]}", city, state)
        except Exception:
            continue
        if not is_firm:
            continue
        candidate["name"] = firm_name_from_title(title) or candidate["name"]
        candidate["quality_score"] = score
        firms.append(candidate)
        if len(firms) >= limit:
            break

    researcher.stats["firms_found"] = len(firms)
    return firms
