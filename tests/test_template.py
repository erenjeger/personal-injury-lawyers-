from exporters.output import COLUMNS, to_frame


EXPECTED_COLUMNS = [
    "attorney_id", "name", "practice_area", "firm", "city", "state",
    "licensed_states", "education", "affiliations", "badges", "photo",
    "years_experience", "rating", "review_count", "phone", "languages",
    "about", "callout_text", "status", "menu_order",
]


def test_template_columns_match_exactly():
    assert COLUMNS == EXPECTED_COLUMNS


def test_template_defaults_are_blank_or_publish():
    df = to_frame([{
        "attorney_id": "PHX-001",
        "name": "Jane Smith",
        "practice_area": "Personal Injury|Car Accidents",
        "firm": "Example Injury Law",
        "city": "Phoenix, AZ",
        "state": "AZ",
        "phone": "(602) 555-0100",
        "about": "Jane Smith is a personal injury attorney. " * 10,
        "source_url": "https://example.com/jane",
        "photo_url": "https://example.com/jane.jpg",
        "confidence": 0.9,
    }])
    assert list(df.columns) == EXPECTED_COLUMNS
    assert df.loc[0, "photo"] == ""
    assert df.loc[0, "callout_text"] == ""
    assert df.loc[0, "status"] == "publish"
