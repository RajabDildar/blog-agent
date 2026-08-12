import base64
import os
import time

import requests


MODEL = os.getenv(
    "CLOUDFLARE_IMAGE_MODEL",
    "@cf/black-forest-labs/flux-1-schnell",
)


def cloudflare_generate_image_bytes(
    prompt: str,
    *,
    max_attempts: int = 2,
) -> bytes:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")

    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")

    if not account_id:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not configured.")

    if not api_token:
        raise RuntimeError("CLOUDFLARE_API_TOKEN is not configured.")

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"

    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
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

            image_base64 = result.get("result", {}).get("image")

            if not image_base64:
                raise RuntimeError("Cloudflare returned no image.")

            try:
                image_bytes = base64.b64decode(image_base64)
            except Exception as exc:
                raise RuntimeError(
                    "Cloudflare returned invalid base64 image data."
                ) from exc

            if not image_bytes:
                raise RuntimeError("Decoded Cloudflare image is empty.")

            return image_bytes

        except Exception as exc:
            last_error = exc

            if attempt < max_attempts:
                time.sleep(2 * attempt)

    raise RuntimeError(
        f"Cloudflare image generation failed after "
        f"{max_attempts} attempts: {last_error}"
    )
