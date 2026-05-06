import pytest

from services.scheduler.app.routing import route_job


def test_explicit_valid_model():
    assert route_job("text-small", "hello") == "text-small"
    assert route_job("text-large", "hello") == "text-large"
    assert route_job("image-small", "hello") == "image-small"


def test_explicit_unknown_model_raises():
    with pytest.raises(ValueError, match="Unknown model"):
        route_job("nonexistent", "hello")


def test_auto_short_text_routes_to_text_small():
    assert route_job("auto", "short text") == "text-small"


def test_auto_long_text_routes_to_text_large():
    long_input = "word " * 50  # 250 chars
    assert route_job("auto", long_input) == "text-large"


def test_auto_dict_with_image_key_routes_to_image_small():
    assert route_job("auto", {"image": "base64data"}) == "image-small"
    assert route_job("auto", {"image_url": "http://example.com/img.jpg"}) == "image-small"


def test_auto_dict_with_short_text_routes_to_text_small():
    assert route_job("auto", {"text": "hello world"}) == "text-small"


def test_auto_dict_with_long_text_routes_to_text_large():
    assert route_job("auto", {"prompt": "word " * 50}) == "text-large"
