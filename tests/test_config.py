"""Tests for scripts/config.py shared configuration."""


def test_reference_categories_is_nonempty_list():
    from scripts.config import DEFAULT_REFERENCE_CATEGORIES

    assert isinstance(DEFAULT_REFERENCE_CATEGORIES, list)
    assert len(DEFAULT_REFERENCE_CATEGORIES) >= 10
    assert "store" in DEFAULT_REFERENCE_CATEGORIES


def test_location_aliases_is_a_dict():
    from scripts.config import KNOWN_LOCATION_ALIASES

    assert isinstance(KNOWN_LOCATION_ALIASES, dict)


def test_price_tiers_are_expected():
    from scripts.config import PRICE_TIERS

    assert PRICE_TIERS == ["low", "mid", "high"]


def test_radius_bounds():
    from scripts.config import RADIUS_MIN_KM, RADIUS_MAX_KM

    assert RADIUS_MIN_KM == 0.5
    assert RADIUS_MAX_KM == 10.0
    assert RADIUS_MIN_KM < RADIUS_MAX_KM


def test_cache_ttls_are_positive():
    from scripts.config import SEARCH_CACHE_TTL_SECONDS, DETAILS_CACHE_TTL_SECONDS

    assert SEARCH_CACHE_TTL_SECONDS > 0
    assert DETAILS_CACHE_TTL_SECONDS > 0
