"""
Run this ONCE to get a reusable YouTube upload token — designed to work from
a phone with no desktop and no local server, using Google's OAuth **device
authorization flow** (the same "go to this URL and type this code" flow smart
TVs use). You can run this script itself on GitHub Actions (see
.github/workflows/youtube-auth-setup.yml) and do everything from your phone's
browser: tap a link, type a code, done.

Setup before running:
  1. https://console.cloud.google.com/ -> create/select a project
  2. Enable "YouTube Data API v3" (APIs & Services -> Library)
  3. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID
     -> Application type: "TVs and Limited Input devices"
     (NOT "Desktop app" — that type doesn't support this flow)
  4. Download the JSON, save it as client_secret.json in this project's root
  5. OAuth consent screen -> add your own Google account as a Test User

What happens when you run it:
  - It prints a short URL and a code.
  - Open that URL on your phone (or any device), log into the Google account
    that owns your channel, and type the code.
  - This script polls in the background and saves token.json once you approve.
"""

import json
import time

import requests

from config import YOUTUBE_CLIENT_SECRETS_FILE, YOUTUBE_TOKEN_FILE, YOUTUBE_UPLOAD_SCOPES

DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _load_client_creds() -> tuple[str, str]:
    if not YOUTUBE_CLIENT_SECRETS_FILE.exists():
        raise FileNotFoundError(
            f"Missing {YOUTUBE_CLIENT_SECRETS_FILE}. Download it from Google Cloud Console "
            "(OAuth client ID, 'TVs and Limited Input devices' type) — see this file's docstring."
        )
    data = json.loads(YOUTUBE_CLIENT_SECRETS_FILE.read_text(encoding="utf-8"))
    # Google's downloaded JSON nests fields under "installed" or "web" depending on client type;
    # limited-input-device clients typically don't nest — handle both shapes defensively.
    block = data.get("installed") or data.get("web") or data
    return block["client_id"], block["client_secret"]


def request_device_code(client_id: str) -> dict:
    resp = requests.post(
        DEVICE_CODE_URL,
        data={"client_id": client_id, "scope": " ".join(YOUTUBE_UPLOAD_SCOPES)},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def poll_for_token(client_id: str, client_secret: str, device_code: str, interval: int) -> dict:
    while True:
        time.sleep(interval)
        resp = requests.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=15,
        )
        payload = resp.json()

        if resp.status_code == 200:
            return payload

        error = payload.get("error")
        if error == "authorization_pending":
            continue  # user hasn't approved yet — keep polling
        elif error == "slow_down":
            interval += 5
            continue
        else:
            raise RuntimeError(f"OAuth device flow failed: {payload}")


def main():
    client_id, client_secret = _load_client_creds()

    device_resp = request_device_code(client_id)
    verification_url = device_resp["verification_url"]
    user_code = device_resp["user_code"]
    interval = device_resp.get("interval", 5)

    print("\n" + "=" * 50)
    print(f"  1. On your phone, open: {verification_url}")
    print(f"  2. Enter this code:     {user_code}")
    print("  3. Log in and approve access for your YouTube channel.")
    print("=" * 50 + "\n")
    print("Waiting for approval...")

    token_resp = poll_for_token(client_id, client_secret, device_resp["device_code"], interval)

    # Save in the same authorized-user format google-auth's Credentials.from_authorized_user_file
    # expects, so upload_youtube.py can load it without any changes.
    token_data = {
        "token": token_resp["access_token"],
        "refresh_token": token_resp["refresh_token"],
        "token_uri": TOKEN_URL,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": YOUTUBE_UPLOAD_SCOPES,
    }
    YOUTUBE_TOKEN_FILE.write_text(json.dumps(token_data), encoding="utf-8")

    print(f"[done] saved reusable token to {YOUTUBE_TOKEN_FILE}")
    print("       For GitHub Actions: copy this file's contents into the YOUTUBE_TOKEN_JSON")
    print("       repo secret. Keep it private — it grants upload access to your channel.")


if __name__ == "__main__":
    main()
