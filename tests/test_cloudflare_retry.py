import requests
from dotenv import load_dotenv

load_dotenv()

from services.cloudflare import cloudflare_generate_image_bytes


def make_response(status_code: int, payload: dict) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = __import__("json").dumps(payload).encode()
    response.url = "https://api.cloudflare.com/client/v4/test"
    return response


def test_cloudflare_400_is_not_retried(monkeypatch):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        return make_response(
            400,
            {
                "success": False,
                "errors": [{"code": 5007, "message": "No such model"}],
            },
        )

    monkeypatch.setattr("services.cloudflare.requests.post", fake_post)

    try:
        cloudflare_generate_image_bytes(
            "test prompt",
            max_attempts=3,
        )
    except RuntimeError as exc:
        assert "Cloudflare image generation failed after 1 attempts" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")

    assert calls == 1


def test_cloudflare_429_is_retried_then_succeeds(monkeypatch):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1

        if calls == 1:
            return make_response(
                429,
                {
                    "success": False,
                    "errors": [{"code": 3040, "message": "Out of capacity"}],
                },
            )

        return make_response(
            200,
            {
                "success": True,
                "result": {
                    "image": "aGVsbG8=",
                },
            },
        )

    monkeypatch.setattr("services.cloudflare.requests.post", fake_post)
    monkeypatch.setattr("services.cloudflare.time.sleep", lambda _: None)

    result = cloudflare_generate_image_bytes(
        "test prompt",
        max_attempts=3,
    )

    assert result == b"hello"
    assert calls == 2


def test_cloudflare_timeout_is_retried(monkeypatch):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1

        if calls == 1:
            raise requests.Timeout("timed out")

        return make_response(
            200,
            {
                "success": True,
                "result": {
                    "image": "aGVsbG8=",
                },
            },
        )

    monkeypatch.setattr("services.cloudflare.requests.post", fake_post)
    monkeypatch.setattr("services.cloudflare.time.sleep", lambda _: None)

    result = cloudflare_generate_image_bytes(
        "test prompt",
        max_attempts=3,
    )

    assert result == b"hello"
    assert calls == 2


def test_cloudflare_500_is_retried(monkeypatch):
    calls = 0

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1

        if calls < 3:
            return make_response(
                500,
                {
                    "success": False,
                    "errors": [{"message": "temporary server error"}],
                },
            )

        return make_response(
            200,
            {
                "success": True,
                "result": {
                    "image": "aGVsbG8=",
                },
            },
        )

    monkeypatch.setattr("services.cloudflare.requests.post", fake_post)
    monkeypatch.setattr("services.cloudflare.time.sleep", lambda _: None)

    result = cloudflare_generate_image_bytes(
        "test prompt",
        max_attempts=3,
    )

    assert result == b"hello"
    assert calls == 3
