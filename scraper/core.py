import re
import time
from collections import OrderedDict
from urllib.parse import urljoin, urlparse, quote_plus
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

DIRECTORY_DOMAINS = {
    "findlaw.com", "avvo.com", "justia.com", "superlawyers.com", "lawyers.com",
    "martindale.com", "martindale-hubbell.com", "yelp.com", "yellowpages.com",
}
BIO_HINTS = ("attorney", "lawyer", "our-team", "team", "professionals", "people", "bio", "profile", "lawyers")
PI_TERMS = ("personal injury", "car accident", "truck accident", "motorcycle accident", "wrongful death", "premises liability", "slip and fall", "injury lawyer", "injury attorney")


class WebResearcher:
    def __init__(self, delay=1.5, timeout=20, max_retries=2):
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AttorneyResearchTool/2.0 (+public-web-research; respectful-rate-limit)"})
        self._robots = {}
        self._cache = {}

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
        return rp is not None and rp.can_fetch(self.session.headers["User-Agent"], url)

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
                if "text/html" not in response.headers.get("content-type", "").lower():
                    return None
                self._cache[url] = response
                time.sleep(self.delay)
                return response
            except requests.RequestException:
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 4))
        return None

    @staticmethod
    def normalize_url(url: str) -> str:
        return url.split("#", 1)[0].rstrip("/")

    @staticmethod
    def is_directory(url: str) -> bool:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in DIRECTORY_DOMAINS)

    def search(self, query: str, limit: int = 30):
        url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
        response = self.get(url)
        if not response:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for a in soup.select("a.result__a")[:limit]:
            href = a.get("href", "")
            if href.startswith("http") and not self.is_directory(href):
                results.append((a.get_text(" ", strip=True), self.normalize_url(href)))
        return list(OrderedDict((u, (t, u)) for t, u in results).values())

    def discover_firms(self, city: str, state: str, limit: int = 20):
        queries = [
            f'"{city}" "{state}" personal injury attorney',
            f'"{city}" "{state}" personal injury law firm',
            f'"{city}" personal injury lawyer',
        ]
        firms, seen_hosts = [], set()
        for q in queries:
            for title, url in self.search(q, limit=50):
                host = urlparse(url).netloc.lower().removeprefix("www.")
                if host in seen_hosts or self.is_directory(url):
                    continue
                seen_hosts.add(host)
                firms.append({"name": self._firm_name(title), "url": url, "domain": host})
                if len(firms) >= limit:
                    return firms
        return firms

    @staticmethod
    def _firm_name(title: str) -> str:
        title = re.sub(r"\s*[-|–].*$", "", title).strip()
        return title or "Unknown Law Firm"

    @staticmethod
    def _links(base_url, soup):
        out = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if href.startswith("http"):
                out.append((a.get_text(" ", strip=True), href))
        return out

    def discover_attorney_pages(self, firm_url: str, max_pages: int = 80):
        response = self.get(firm_url)
        if not response:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        candidates = []
        for text, href in self._links(firm_url, soup):
            hay = f"{text} {href}".lower()
            if any(h in hay for h in BIO_HINTS):
                candidates.append(href)
        likely = sorted(set(candidates), key=lambda u: 0 if any(x in u.lower() for x in ("attorney", "lawyer", "team", "people", "bio")) else 1)
        for href in likely[:12]:
            r = self.get(href)
            if not r:
                continue
            s = BeautifulSoup(r.text, "html.parser")
            for text, link in self._links(href, s):
                hay = f"{text} {link}".lower()
                if any(h in hay for h in BIO_HINTS):
                    candidates.append(link)
            if len(candidates) >= max_pages:
                break
        unique, seen = [], set()
        for url in candidates:
            url = self.normalize_url(url)
            if url not in seen and not self.is_directory(url) and urlparse(url).netloc == urlparse(firm_url).netloc:
                seen.add(url)
                unique.append(url)
        return unique[:max_pages]

    @staticmethod
    def _clean(value):
        return re.sub(r"\s+", " ", value or "").strip()

    @staticmethod
    def _visible_text(soup):
        clone = BeautifulSoup(str(soup), "html.parser")
        for tag in clone(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
            tag.decompose()
        return WebResearcher._clean(clone.get_text(" ", strip=True))

    @staticmethod
    def _meta(soup, *names):
        for name in names:
            node = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
            if node and node.get("content"):
                return WebResearcher._clean(node["content"])
        return ""

    @staticmethod
    def _jsonld(soup):
        import json
        objects = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text())
                objects.extend(data if isinstance(data, list) else [data])
            except Exception:
                continue
        return objects

    def extract_profile(self, url: str, city: str, state: str, firm_name: str):
        response = self.get(url)
        if not response:
            return None
        soup = BeautifulSoup(response.text, "html.parser")
        text = self._visible_text(soup)
        title = self._clean(soup.title.get_text(" ", strip=True) if soup.title else "")
        jsonld = self._jsonld(soup)

        name = ""
        for obj in jsonld:
            if isinstance(obj, dict) and str(obj.get("@type", "")).lower() in {"person", "attorney"} and obj.get("name"):
                name = self._clean(str(obj["name"]))
                break
        if not name:
            for h in soup.find_all(["h1", "h2"]):
                candidate = self._clean(h.get_text(" ", strip=True))
                if 2 <= len(candidate.split()) <= 8 and not any(x in candidate.lower() for x in ("practice", "contact", "personal injury", "our team")):
                    name = candidate
                    break
        if not name:
            name = re.split(r"\s*[|–-]\s*", title)[0].strip()

        phone = ""
        tel = soup.select_one('a[href^="tel:"]')
        if tel:
            phone = self._clean(tel.get_text(" ", strip=True)) or tel.get("href", "").replace("tel:", "")
        if not phone:
            m = re.search(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", text)
            phone = m.group(0) if m else ""

        image_url = ""
        for obj in jsonld:
            if isinstance(obj, dict) and obj.get("image"):
                image_url = urljoin(url, obj["image"] if isinstance(obj["image"], str) else obj["image"].get("url", ""))
                if image_url:
                    break
        if not image_url:
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                alt = (img.get("alt") or "").lower()
                if src and ("attorney" in alt or "lawyer" in alt or (name and name.split()[0].lower() in alt)):
                    image_url = urljoin(url, src)
                    break

        practice = self._extract_section(soup, text, ("practice areas", "practice area", "areas of practice"))
        licensed = self._extract_section(soup, text, ("bar admissions", "admissions", "admitted", "licensed"))
        education = self._extract_section(soup, text, ("education", "law school"))
        affiliations = self._extract_section(soup, text, ("memberships", "affiliations", "professional associations"))
        languages = self._extract_section(soup, text, ("languages", "language"))
        if not practice:
            practice = self._keyword_context(text, PI_TERMS)

        combined = f"{practice} {text}".lower()
        pi_score = sum(1 for term in PI_TERMS if term in combined)
        confidence = min(1.0, 0.25 + 0.15 * min(pi_score, 3) + (0.2 if phone else 0) + (0.2 if image_url else 0) + (0.15 if name else 0))

        return {
            "name": name, "practice_area": practice, "firm": firm_name, "city": f"{city}, {state}", "state": state,
            "licensed_states": licensed, "education": education, "affiliations": affiliations,
            "badges": self._badges(text), "phone": phone, "languages": languages, "about": text,
            "source_url": url, "photo_url": image_url, "email": self._email(soup), "confidence": round(confidence, 2),
        }

    @staticmethod
    def _email(soup):
        mail = soup.select_one('a[href^="mailto:"]')
        return mail.get("href", "").replace("mailto:", "").split("?", 1)[0] if mail else ""

    @staticmethod
    def _extract_section(soup, text, labels):
        # First try headings and the next few sibling/list nodes for cleaner structured data.
        for heading in soup.find_all(re.compile("^h[1-6]$")):
            h = WebResearcher._clean(heading.get_text(" ", strip=True)).lower()
            if any(label in h for label in labels):
                parts = []
                node = heading.find_next_sibling()
                for _ in range(4):
                    if not node:
                        break
                    value = WebResearcher._clean(node.get_text(" ", strip=True))
                    if value:
                        parts.append(value)
                    node = node.find_next_sibling()
                if parts:
                    return " | ".join(parts)[:1000]
        return WebResearcher._keyword_context(text, labels)

    @staticmethod
    def _keyword_context(text, labels):
        lower = text.lower()
        for label in labels:
            idx = lower.find(label.lower())
            if idx >= 0:
                return text[idx:idx + 800]
        return ""

    @staticmethod
    def _badges(text):
        lower = text.lower()
        found = []
        if "free consultation" in lower or "free initial consultation" in lower:
            found.append("free_consultation")
        if "contingency fee" in lower or "contingency fees" in lower:
            found.append("contingency_fee")
        if "same day" in lower and ("consult" in lower or "appointment" in lower):
            found.append("same_day_match")
        return "|".join(found)
