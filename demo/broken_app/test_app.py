"""The demo crash as a test: fails until get_product copes with no price."""

from app import get_product


def test_get_product_apple_does_not_raise():
    assert get_product("apple") is not None
