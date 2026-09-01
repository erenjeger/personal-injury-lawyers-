import json
import re
import time
from collections import OrderedDict
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

DIRECTORY_DOMAINS = {
    "findlaw.com", "avvo.com", "justia.com", "superlawyers.com", "lawyers.com",
    "martindale.com", "martindale-hubbell.com", "yelp.com", "yellowpages.com",
    "lawinfo.com", "nolo.com", "lawyers.findlaw.com", "lawtally.com",
}
BIO_HINTS = (
    "attorney", "lawyer", "our-team", "team", "professionals", "people",
    "bio", "profile", "lawyers", "attorneys", "staff",
)
PI_TERMS = (
    "personal injury", "car accident", "truck accident", "motorcycle accident",
    "wrongful death", "premises liability", "slip and fall", "product liability",
    "pedestrian accident", "catastrophic injury", "injury lawyer", "injury attorney",
)
BADGE_PATTERNS = {
    "free_consultation": ("free consultation", "free initial consultation", "complimentary consultation"),
    "contingency_fee": ("contingency fee", "contingency fees", "no fee unless we win"),
    "same_day_match": ("same day consultation", "same-day consultation", "same day appointment", "same-day appointment"),
}


class WebResearcher:
    def __init__(self, delay=1.5, timeout=20, max_retries=2, strict_robots=False):
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.strict_robots = strict_robots
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36 AttorneyResearchTool/3.0"
        })
        self._robots = {}
        self._cache = {}
        self.stats = {
            "search_requests": 0, "pages_fetched": 0, "blocked_robots": 0,
            "failed_requests": 0, "firms_found": 0, "profile_pages_found": 0,
            "profiles_extracted": 0,
        }
        self.last_search_error = ""
        self.search_engine_used = ""

    @staticmethod
    def normalize_url(url: str) -> str:
        return url.split("#", 1)[0].rstrip("/")

    @staticmethod
    def host(url: str) -> str:
        return urlparse(url).netloc.lower().removeprefix("www.").split(":", 1)[0]

    @staticmethod
    def is_directory(url: str) -> bool:
        host = WebResearcher.host(url)
        return any(host == d or host.endswith("." + d) for d in DIRECTORY_DOMAINS)

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        if p.scheme not in {"http", "https"}:
            return False
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp = RobotFileParser()
            rp.set_url(urljoin(root, "/robots.txt"))
            try:
                rp.read()
                self._robots[root] = rp
            except Exception:
                self._robots[root] = None
        rp = self._robots[root]
        if rp is None:
            return not self.strict_robots
        ok = rp.can_fetch(self.session.headers["User-Agent"], url)
        if not ok:
            self.stats["blocked_robots"] += 1
        return ok

    def get(self, url: str):
        url = self.normalize_url(url)
        if url in self._cache:
            return self._cache[url]
        if not self.allowed(url):
            return None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "application/xhtml" not in content_type:
                    return None
                self._cache[url] = response
                self.stats["pages_fetched"] += 1
                if self.delay:
                    time.sleep(self.delay)
                return response
            except requests.RequestException as exc:
                self.stats["failed_requests"] += 1
                self.last_search_error = str(exc)
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 4))
        return None

    def _search_request(self, url: str):
        for attempt in range(self.max_retries + 1):
            try:
                r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                r.raise_for_status()
                if "text/html" not in r.headers.get("content-type", "").lower():
                    return None
                if self.delay:
                    time.sleep(self.delay)
                return r
            except requests.RequestException as exc:
                self.last_search_error = str(exc)
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 4))
        return None

    def search(self, query: str, limit: int = 30):
        engines = [
            ("bing", "https://www.bing.com/search?q=" + quote_plus(query), "li.b_algo h2 a"),
            ("duckduckgo", "https://html.duckduckgo.com/html/?q=" + quote_plus(query), "a.result__a"),
            ("google", "https://www.google.com/search?q=" + quote_plus(query), "div.MjjYud a"),
        ]
        for engine, url, selector in engines:
            self.stats["search_requests"] += 1
            response = self._search_request(url)
            if not response:
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            anchors = soup.select(selector)
            if engine == "google" and not anchors:
                anchors = soup.find_all("a", href=True)
            results = []
            for a in anchors:
                href = a.get("href", "")
                text = self._clean(a.get_text(" ", strip=True))
                if href.startswith("/url?q="):
                    href = href.split("/url?q=", 1)[1].split("&", 1)[0]
                if href.startswith("http") and text and not self.is_directory(href):
                    results.append((text, self.normalize_url(href)))
                if len(results) >= limit:
                    break
            if results:
                self.search_engine_used = engine
                self.last_search_error = ""
                return list(OrderedDict((u, (t, u)) for t, u in results).values())
        self.last_search_error = self.last_search_error or "All configured search engines returned no usable results."
        return []

    def discover_firms(self, city: str, state: str, limit: int = 20):
        queries = [
            f'"{city}" "{state}" personal injury attorney',
            f'"{city}" "{state}" personal injury law firm',
            f'"{city}" personal injury lawyer',
            f'personal injury attorney "{city}"',
        ]
        firms, seen_hosts = [], set()
        for query in queries:
            for title, url in self.search(query, limit=50):
                host = self.host(url)
                if host in seen_hosts or self.is_directory(url):
                    continue
                seen_hosts.add(host)
                firms.append({"name": self._firm_name(title), "url": url, "domain": host})
                if len(firms) >= limit:
                    self.stats["firms_found"] = len(firms)
                    return firms
        self.stats["firms_found"] = len(firms)
        return firms

    @staticmethod
    def _firm_name(title: str) -> str:
        value = re.sub(r"\s*[-|–].*$", "", title).strip()
        return value or "Unknown Law Firm"

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip()

    @staticmethod
    def _links(base_url, soup):
        out = []
        base_host = WebResearcher.host(base_url)
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if href.startswith(("http://", "https://")) and WebResearcher.host(href) == base_host:
                out.append((WebResearcher._clean(a.get_text(" ", strip=True)), WebResearcher.normalize_url(href)))
        return out

    def discover_attorney_pages(self, firm_url: str, max_pages: int = 80):
        response = self.get(firm_url)
        if not response:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        links = self._links(firm_url, soup)
        candidates = []
        team_pages = []
        for text, href in links:
            hay = f"{text} {href}".lower()
            if any(h in hay for h in BIO_HINTS):
                candidates.append(href)
            if any(x in text.lower() for x in ("meet the team", "our attorneys", "our lawyers", "professionals", "people", "attorneys")):
                team_pages.append(href)
        for team_url in list(dict.fromkeys(team_pages))[:10]:
            team_response = self.get(team_url)
            if not team_response:
                continue
            team_soup = BeautifulSoup(team_response.text, "html.parser")
            for text, link in self._links(team_url, team_soup):
                hay = f"{text} {link}".lower()
                if any(h in hay for h in BIO_HINTS) or 2 <= len(text.split()) <= 6:
                    candidates.append(link)
        unique, seen = [], set()
        for url in candidates:
            url = self.normalize_url(url)
            if url not in seen and not self.is_directory(url) and url != self.normalize_url(firm_url):
                seen.add(url)
                unique.append(url)
        self.stats["profile_pages_found"] += len(unique)
        return unique[:max_pages]

    @staticmethod
    def _jsonld(soup):
        objects = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text())
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and isinstance(data.get("@graph"), list):
                objects.extend(data["@graph"])
            elif isinstance(data, list):
                objects.extend(data)
            elif isinstance(data, dict):
                objects.append(data)
        return [obj for obj in objects if isinstance(obj, dict)]

    @staticmethod
    def _type_matches(obj, types):
        raw = obj.get("@type", "")
        values = raw if isinstance(raw, list) else [raw]
        return any(str(v).lower() in types for v in values)

    @staticmethod
    def _text_from_node(node):
        return WebResearcher._clean(node.get_text(" ", strip=True)) if node else ""

    def _profile_container(self, soup):
        selectors = [
            "article", "main", ".attorney-bio", ".lawyer-bio", ".attorney-profile",
            ".lawyer-profile", ".profile-content", ".bio-content", ".bio", ".profile",
        ]
        containers = []
        for selector in selectors:
            containers.extend(soup.select(selector))
        if not containers:
            return soup
        # Prefer a container with both a person's name and a substantial amount of text.
        return max(containers, key=lambda x: len(self._text_from_node(x)))

    def _visible_text(self, node):
        clone = BeautifulSoup(str(node), "html.parser")
        for tag in clone(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
            tag.decompose()
        return self._clean(clone.get_text(" ", strip=True))

    def _bio_text(self, container):
        # Keep the complete profile content while removing obvious navigation/contact noise.
        clone = BeautifulSoup(str(container), "html.parser")
        for tag in clone(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
            tag.decompose()
        blocks = []
        for tag in clone.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
            value = self._clean(tag.get_text(" ", strip=True))
            if len(value) >= 25:
                blocks.append(value)
        if blocks:
            return "\n\n".join(dict.fromkeys(blocks))
        return self._clean(clone.get_text(" ", strip=True))

    def _find_name(self, soup, jsonld, title):
        for obj in jsonld:
            if self._type_matches(obj, {"person", "attorney"}) and obj.get("name"):
                return self._clean(str(obj["name"]))
        for selector in ("h1", ".attorney-name", ".lawyer-name", ".profile-name"):
            for node in soup.select(selector):
                value = self._clean(node.get_text(" ", strip=True))
                if 2 <= len(value.split()) <= 8 and not any(x in value.lower() for x in ("personal injury", "contact us", "our team")):
                    return value
        candidate = re.split(r"\s*[|–-]\s*", title)[0].strip()
        return candidate if 2 <= len(candidate.split()) <= 8 else ""

    def _find_phone(self, soup, text):
        tel = soup.select_one('a[href^="tel:"]')
        if tel:
            value = self._clean(tel.get_text(" ", strip=True))
            return value or tel.get("href", "").replace("tel:", "").strip()
        match = re.search(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", text)
        return match.group(0) if match else ""

    def _find_image(self, soup, jsonld, page_url, name):
        for obj in jsonld:
            image = obj.get("image")
            if image and self._type_matches(obj, {"person", "attorney"}):
                value = image if isinstance(image, str) else image.get("url", "") if isinstance(image, dict) else ""
                if value:
                    return urljoin(page_url, value)
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or img.get("data-original")
            if not src:
                continue
            alt = self._clean(img.get("alt", "")).lower()
            cls = " ".join(img.get("class", [])).lower()
            if any(term in alt + " " + cls for term in ("attorney", "lawyer", "headshot", "portrait")) or (name and name.split()[0].lower() in alt):
                return urljoin(page_url, src)
        return ""

    def _section_values(self, container, labels):
        wanted = {x.lower() for x in labels}
        headings = container.find_all(re.compile(r"^h[1-6]$"))
        for heading in headings:
            label = self._clean(heading.get_text(" ", strip=True)).lower().rstrip(":")
            if not any(x in label for x in wanted):
                continue
            values = []
            node = heading.find_next_sibling()
            for _ in range(8):
                if not node or getattr(node, "name", None) in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                    break
                if getattr(node, "name", None) in {"ul", "ol"}:
                    values.extend(self._clean(li.get_text(" ", strip=True)) for li in node.find_all("li"))
                else:
                    value = self._clean(node.get_text(" ", strip=True))
                    if value:
                        values.append(value)
                node = node.find_next_sibling()
            values = [v for v in dict.fromkeys(values) if v]
            if values:
                return values
        return []

    def _keyword_section(self, text, labels):
        lower = text.lower()
        for label in labels:
            idx = lower.find(label.lower())
            if idx < 0:
                continue
            chunk = text[idx:idx + 700]
            chunk = re.split(r"\b(?:education|affiliations|memberships|languages|bar admissions|practice areas)\b", chunk, flags=re.I)[0]
            return self._clean(chunk).strip(" :-")
        return ""

    def _practice_area(self, container, text):
        values = self._section_values(container, ("practice areas", "practice area", "areas of practice", "areas we handle"))
        if values:
            items = []
            for value in values:
                parts = re.split(r"\s*[|•;,]\s*|\s{2,}", value)
                items.extend(p.strip() for p in parts if p.strip())
            return "|".join(dict.fromkeys(items))
        context = self._keyword_section(text, ("practice areas", "practice area", "areas of practice"))
        if context:
            return context
        found = [term.title() for term in PI_TERMS if term in text.lower()]
        return "|".join(dict.fromkeys(found))

    def _licensed_states(self, container, text, state):
        values = self._section_values(container, ("bar admissions", "admissions", "admitted", "licensed", "bar memberships"))
        raw = " | ".join(values) if values else self._keyword_section(text, ("bar admissions", "admissions", "admitted", "licensed"))
        states = []
        for abbr, full in {
            "AL": "Alabama", "AZ": "Arizona", "CA": "California", "CO": "Colorado", "DC": "District of Columbia",
            "FL": "Florida", "GA": "Georgia", "IL": "Illinois", "MD": "Maryland", "NY": "New York", "TX": "Texas",
            "VA": "Virginia", "WA": "Washington", "NV": "Nevada", "UT": "Utah", "OR": "Oregon", "PA": "Pennsylvania",
        }.items():
            if re.search(rf"\b{re.escape(abbr)}\b", raw) or re.search(rf"\b{re.escape(full)}\b", raw, re.I):
                states.append(abbr)
        if not states and state:
            if re.search(rf"\b{re.escape(state)}\b", raw):
                states.append(state)
        return "|".join(dict.fromkeys(states))

    def _simple_section(self, container, text, labels):
        values = self._section_values(container, labels)
        if values:
            return "|".join(dict.fromkeys(values))
        return self._keyword_section(text, labels)

    def _rating(self, jsonld):
        for obj in jsonld:
            aggregate = obj.get("aggregateRating")
            if isinstance(aggregate, dict):
                try:
                    value = float(aggregate.get("ratingValue"))
                    if 0 <= value <= 5:
                        return value
                except (TypeError, ValueError):
                    pass
        return None

    def _review_count(self, jsonld):
        for obj in jsonld:
            aggregate = obj.get("aggregateRating")
            if isinstance(aggregate, dict):
                try:
                    value = int(float(aggregate.get("reviewCount", aggregate.get("ratingCount"))))
                    if value >= 0:
                        return value
                except (TypeError, ValueError):
                    pass
        return None

    def _years_experience(self, text):
        matches = re.findall(r"\b(\d{1,2})\s*\+?\s*years?\s+(?:of\s+)?experience\b", text, flags=re.I)
        if matches:
            return int(max(matches, key=int))
        years = re.findall(r"(?:admitted|licensed|bar admission|joined the bar)[^\d]{0,80}(?:19|20)(\d{2})", text, flags=re.I)
        if years:
            admission_year = int("20" + years[0]) if len(years[0]) == 2 else int(years[0])
            current_year = time.localtime().tm_year
            if 1950 <= admission_year <= current_year:
                return current_year - admission_year
        return None

    def _badges(self, text):
        lower = text.lower()
        return "|".join(key for key, patterns in BADGE_PATTERNS.items() if any(p in lower for p in patterns))

    def _confidence(self, name, practice, phone, about, photo, source_url):
        score = 0.0
        score += 0.20 if name else 0
        score += 0.25 if practice else 0
        score += 0.20 if phone else 0
        score += 0.20 if len(about) >= 150 else 0.10 if len(about) >= 75 else 0
        score += 0.10 if photo else 0
        score += 0.05 if source_url else 0
        return round(min(score, 1.0), 2)

    def extract_profile(self, url: str, city: str, state: str, firm_name: str):
        response = self.get(url)
        if not response:
            return None
        soup = BeautifulSoup(response.text, "html.parser")
        jsonld = self._jsonld(soup)
        container = self._profile_container(soup)
        title = self._clean(soup.title.get_text(" ", strip=True) if soup.title else "")
        name = self._find_name(container, jsonld, title)
        page_text = self._visible_text(container)
        about = self._bio_text(container)
        practice = self._practice_area(container, page_text)
        phone = self._find_phone(container, page_text)
        photo_url = self._find_image(container, jsonld, url, name)
        education = self._simple_section(container, page_text, ("education", "law school", "degrees"))
        affiliations = self._simple_section(container, page_text, ("memberships", "affiliations", "professional associations", "bar associations"))
        languages = self._simple_section(container, page_text, ("languages", "language"))
        licensed_states = self._licensed_states(container, page_text, state)
        rating = self._rating(jsonld)
        review_count = self._review_count(jsonld)
        years = self._years_experience(page_text)
        confidence = self._confidence(name, practice, phone, about, photo_url, url)
        self.stats["profiles_extracted"] += 1
        return {
            "name": name,
            "practice_area": practice,
            "firm": firm_name,
            "city": f"{city}, {state}",
            "state": state,
            "licensed_states": licensed_states,
            "education": education,
            "affiliations": affiliations,
            "badges": self._badges(page_text),
            "photo": "",
            "years_experience": years,
            "rating": rating,
            "review_count": review_count,
            "phone": phone,
            "languages": languages,
            "about": about,
            "callout_text": "",
            "status": "publish",
            "source_url": url,
            "photo_url": photo_url,
            "confidence": confidence,
        }
