from scraper.pipeline import attorney_id, normalize_name, quality_check


def test_attorney_id():
    assert attorney_id("PHX", 1) == "PHX-001"
    assert attorney_id("BAL", 40) == "BAL-040"


def test_normalize_name():
    assert normalize_name("Jane Q. Smith") == "janeqsmith"


def test_quality_accepts_personal_injury_profile():
    raw = {
        "name": "Jane Smith",
        "practice_area": "Personal Injury | Car Accidents",
        "phone": "602-555-0100",
        "about": "Jane Smith is a personal injury attorney with extensive experience representing injured clients. " * 3,
    }
    ok, reason = quality_check(raw)
    assert ok
    assert reason == "ok"


def test_quality_rejects_missing_phone():
    raw = {"name": "Jane Smith", "practice_area": "Personal Injury", "phone": "", "about": "A" * 200}
    ok, reason = quality_check(raw)
    assert not ok
    assert "phone" in reason
