import base64
import os

import requests


MODEL = os.getenv(
    "CLOUDFLARE_IMAGE_MODEL",
    "@cf/black-forest-labs/flux-1-schnell",
)


def cloudflare_generate_image_bytes(
    prompt: str,
) -> bytes:
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]

    api_token = os.environ["CLOUDFLARE_API_TOKEN"]

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"

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
        raise RuntimeError(f"Cloudflare error: {result}")

    image_base64 = result["result"].get("image")

    if not image_base64:
        raise RuntimeError("Cloudflare returned no image.")

    return base64.b64decode(image_base64)
