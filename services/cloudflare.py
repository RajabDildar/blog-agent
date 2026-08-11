import base64
import os

import requests


def cloudflare_generate_image_bytes(prompt: str) -> bytes:
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    api_token = os.environ["CLOUDFLARE_API_TOKEN"]

    model = "@cf/black-forest-labs/flux-1-schnell"

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": prompt,
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            f"Cloudflare image generation failed: "
            f"{response.status_code} {response.text}"
        )

    result = response.json()

    if not result.get("success"):
        raise RuntimeError(f"Cloudflare returned an unsuccessful response: {result}")

    image_base64 = result["result"].get("image")

    if not image_base64:
        raise RuntimeError("Cloudflare returned no image data.")

    return base64.b64decode(image_base64)
