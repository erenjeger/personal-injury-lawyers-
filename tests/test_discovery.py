from scraper.discovery import blocked_domain, candidate_score, page_score


def test_directory_and_noise_domains_are_blocked():
    assert blocked_domain("https://www.thefreedictionary.com/personal-injury")
    assert blocked_domain("https://www.justia.com/lawyers/personal-injury")
    assert blocked_domain("https://www.bing.com/ck/a/?u=example")
    assert not blocked_domain("https://exampleinjurylaw.com/attorneys")


def test_candidate_score_prefers_relevant_law_firm():
    score = candidate_score(
        "Phoenix Personal Injury Attorneys | Example Law Firm",
        "https://exampleinjurylaw.com/",
        "Phoenix",
        "AZ",
    )
    assert score >= 8


def test_page_score_accepts_first_party_pi_firm():
    score, is_firm = page_score(
        "Example Law Firm Attorneys personal injury practice areas Phoenix AZ free consultation",
        "Phoenix",
        "AZ",
    )
    assert score >= 5
    assert is_firm
