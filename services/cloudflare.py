import base64
import os
import random
import time

import requests

MODEL = os.getenv(
    "CLOUDFLARE_IMAGE_MODEL",
    "@cf/black-forest-labs/flux-1-schnell",
)


TRANSIENT_HTTP_STATUS_CODES = {
    408,
    429,
}


DEFAULT_MAX_ATTEMPTS = 5


def _is_transient_cloudflare_error(
    exc: Exception,
) -> bool:
    if isinstance(
        exc,
        (
            requests.Timeout,
            requests.ConnectionError,
        ),
    ):
        return True

    if isinstance(
        exc,
        requests.HTTPError,
    ):
        response = exc.response

        if response is None:
            return False

        status_code = response.status_code

        return status_code in TRANSIENT_HTTP_STATUS_CODES or 500 <= status_code <= 599

    return False


def _get_retry_after_seconds(
    exc: Exception,
) -> float | None:
    if not isinstance(
        exc,
        requests.HTTPError,
    ):
        return None

    response = exc.response

    if response is None:
        return None

    retry_after = response.headers.get(
        "retry-after",
    )

    if retry_after is None:
        return None

    try:
        return float(retry_after)
    except ValueError:
        return None


def _calculate_retry_delay(
    exc: Exception,
    attempt: int,
) -> float:
    retry_after = _get_retry_after_seconds(
        exc,
    )

    if retry_after is not None:
        return retry_after

    exponential_backoff = 2**attempt

    jitter = random.uniform(
        0,
        1,
    )

    return exponential_backoff + jitter


def cloudflare_generate_image_bytes(
    prompt: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> bytes:
    account_id = os.environ.get(
        "CLOUDFLARE_ACCOUNT_ID",
    )

    api_token = os.environ.get(
        "CLOUDFLARE_API_TOKEN",
    )

    if not account_id:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not configured.")

    if not api_token:
        raise RuntimeError("CLOUDFLARE_API_TOKEN is not configured.")

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"

    last_error: Exception | None = None
    attempts = 0

    for attempt in range(
        1,
        max_attempts + 1,
    ):
        attempts = attempt

        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": (f"Bearer {api_token}"),
                    "Content-Type": "application/json",
                },
                json={
                    "prompt": prompt,
                },
                timeout=120,
            )

            response.raise_for_status()

            result = response.json()

            if not result.get("success"):
                raise RuntimeError(f"Cloudflare API error: {result}")

            image_base64 = result.get(
                "result",
                {},
            ).get(
                "image",
            )

            if not image_base64:
                raise RuntimeError("Cloudflare returned no image.")

            try:
                image_bytes = base64.b64decode(
                    image_base64,
                )
            except Exception as exc:
                raise RuntimeError(
                    "Cloudflare returned invalid base64 image data."
                ) from exc

            if not image_bytes:
                raise RuntimeError("Decoded Cloudflare image is empty.")

            return image_bytes

        except Exception as exc:
            last_error = exc

            if attempt >= max_attempts or not _is_transient_cloudflare_error(exc):
                break

            delay = _calculate_retry_delay(
                exc,
                attempt,
            )

            time.sleep(
                delay,
            )

    raise RuntimeError(
        f"Cloudflare image generation failed after {attempts} attempts: {last_error}"
    )
