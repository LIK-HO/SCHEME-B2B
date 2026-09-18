from scheme_b2b.normalization import (
    is_valid_email,
    is_valid_phone,
    normalize_phone,
    normalize_website,
)


def test_phone_normalization_and_validation():
    assert normalize_phone("8 (999) 123-45-67") == "79991234567"
    assert is_valid_phone("79991234567")
    assert not is_valid_phone("123")


def test_email_and_website_validation():
    assert is_valid_email("Sales@Example.RU")
    assert not is_valid_email("not-an-email")
    assert normalize_website("example.ru") == "https://example.ru"
    assert normalize_website("not a url") == ""
