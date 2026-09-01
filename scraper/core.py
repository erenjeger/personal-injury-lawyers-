import re
import time
from collections import OrderedDict
from urllib.parse import urljoin, urlparse, quote_plus
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


DIRECTORY_DOMAINS = {
    "findlaw.com", "avvo.com", "justia.com", "superlawyers.com",
    "lawyers.com", "martindale.com", "martindale-hubbell.com",
}

BIO_HINTS = ("attorney", "lawyer", "lawyers", "our-team", "team", "professionals", "people", "bio", "profile")


class WebResearcher:
    def __init__(self, delay=1.5, timeout=20):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AttorneyResearchTool/1.0 (+public-web-research; respectful-rate-limit)"
        })
        self._robots = {}

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
            except Exception:
                # If robots.txt cannot be fetched, do not assume permission for aggressive crawling.
                self._robots[root] = None
            else:
                self._robots[root] = rp
        rp = self._robots[root]
        return rp is not None and rp.can_fetch(self.session.headers["User-Agent"], url)

    def get(self, url: str):
        if not self.allowed(url):
            return None
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            time.sleep(self.delay)
            return response
        except requests.RequestException:
            return None

    @staticmethod
    def normalize_url(url: str) -> str:
        return url.split("#", 1)[0].rstrip("/")

    @staticmethod
    def is_directory(url: str) -> bool:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in DIRECTORY_DOMAINS)

    def search(self, query: str, limit: int = 30):
        # DuckDuckGo HTML is used as a lightweight discovery source; it is not used as the data source.
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
            f"{city} {state} personal injury attorney law firm",
            f"{city} {state} personal injury lawyer firm",
        ]
        firms = []
        seen = set()
        for q in queries:
            for title, url in self.search(q, limit=30):
                host = urlparse(url).netloc.lower()
                if host in seen or self.is_directory(url):
                    continue
                seen.add(host)
                firms.append({"name": title, "url": url})
                if len(firms) >= limit:
                    return firms
        return firms

    @staticmethod
    def _links(base_url, soup):
        out = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if href.startswith("http"):
                out.append((a.get_text(" ", strip=True), href))
        return out

    def discover_attorney_pages(self, firm_url: str, max_pages: int = 60):
        response = self.get(firm_url)
        if not response:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        candidates = []
        for text, href in self._links(firm_url, soup):
            hay = (text + " " + href).lower()
            if any(h in hay for h in BIO_HINTS):
                candidates.append(href)
        # Visit likely team pages once and collect their attorney links.
        for href in list(dict.fromkeys(candidates))[:8]:
            r = self.get(href)
            if not r:
                continue
            s = BeautifulSoup(r.text, "html.parser")
            for text, link in self._links(href, s):
                hay = (text + " " + link).lower()
                if any(h in hay for h in BIO_HINTS):
                    candidates.append(link)
            if len(candidates) >= max_pages:
                break
        unique = []
        seen = set()
        for url in candidates:
            url = self.normalize_url(url)
            if url not in seen and not self.is_directory(url):
                seen.add(url)
                unique.append(url)
        return unique[:max_pages]

    @staticmethod
    def _clean(value):
        return re.sub(r"\s+", " ", value or "").strip()

    def extract_profile(self, url: str, city: str, state: str, firm_name: str):
        response = self.get(url)
        if not response:
            return None
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = self._clean(soup.get_text(" ", strip=True))
        title = self._clean(soup.title.get_text(" ", strip=True) if soup.title else "")

        # Prefer H1/H2 as the name signal.
        name = ""
        for h in soup.find_all(["h1", "h2"]):
            candidate = self._clean(h.get_text(" ", strip=True))
            if 2 <= len(candidate.split()) <= 8 and not any(x in candidate.lower() for x in ("practice", "contact", "personal injury")):
                name = candidate
                break
        if not name:
            name = title.split("|")[0].split("-")[0].strip()

        phone = ""
        tel = soup.select_one('a[href^="tel:"]')
        if tel:
            phone = self._clean(tel.get_text(" ", strip=True)) or tel.get("href", "").replace("tel:", "")
        else:
            m = re.search(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", text)
            phone = m.group(0) if m else ""

        email = ""
        mail = soup.select_one('a[href^="mailto:"]')
        if mail:
            email = mail.get("href", "").replace("mailto:", "").split("?", 1)[0]

        image_url = ""
        for img in soup.find_all("img", src=True):
            alt = (img.get("alt") or "").lower()
            src = img.get("src")
            if src and (name.lower().split()[0] in alt or "attorney" in alt or "lawyer" in alt):
                image_url = urljoin(url, src)
                break

        return {
            "name": name,
            "practice_area": self._extract_labeled(text, ["practice areas", "practice area", "areas of practice"]),
            "firm": firm_name,
            "city": f"{city}, {state}",
            "state": state,
            "licensed_states": self._extract_labeled(text, ["admitted", "admissions", "bar admissions", "licensed"]),
            "education": self._extract_labeled(text, ["education", "law school"]),
            "affiliations": self._extract_labeled(text, ["memberships", "affiliations", "professional associations"]),
            "badges": self._badges(text),
            "phone": phone,
            "languages": self._extract_labeled(text, ["languages", "language"]),
            "about": text,
            "source_url": url,
            "photo_url": image_url,
            "email": email,
        }

    @staticmethod
    def _extract_labeled(text, labels):
        lower = text.lower()
        for label in labels:
            idx = lower.find(label)
            if idx >= 0:
                chunk = text[idx: idx + 500]
                return chunk[:500]
        return ""

    @staticmethod
    def _badges(text):
        lower = text.lower()
        found = []
        if "free consultation" in lower or "free initial consultation" in lower:
            found.append("free_consultation")
        if "contingency fee" in lower or "contingency fees" in lower:
            found.append("contingency_fee")
        if "same day" in lower and "consult" in lower:
            found.append("same_day_match")
        return "|".join(found)
