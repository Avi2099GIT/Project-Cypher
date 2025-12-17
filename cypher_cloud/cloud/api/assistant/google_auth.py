# cloud/api/assistant/google_auth.py
from __future__ import annotations

import os
import pickle
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError

# Base = .../cypher_cloud/cloud/api/assistant
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Go up to .../cypher_cloud
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(BASE_DIR)))
KEYS_DIR = os.path.join(PROJECT_ROOT, "keys")

CREDS_FILE = os.path.join(KEYS_DIR, "google_credentials.json")
TOKEN_FILE = os.path.join(KEYS_DIR, "google_token.pickle")

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]


def get_google_creds() -> Credentials:
    """
    Load (or fetch + store) OAuth2 credentials for Google APIs.
    """
    if not os.path.exists(CREDS_FILE):
        raise FileNotFoundError(
            "Google credentials file not found at:\n"
            f"{CREDS_FILE}\n"
            "Make sure google_credentials.json exists in /keys/ under cypher_cloud."
        )

    creds: Optional[Credentials] = None

    # Load existing token, if any
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "rb") as f:
                creds = pickle.load(f)
        except Exception:
            # Corrupt pickle or other issue
            creds = None

    # Refresh or run OAuth flow
    # We verify validity or force refresh
    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except RefreshError:
                # Token revoked or expired hard -> Must re-login
                print("[GoogleAuth] Refresh failed (revoked/expired). Triggering re-auth.")
                creds = None
            except Exception as e:
                print(f"[GoogleAuth] Unexpected refresh error: {e}. Triggering re-auth.")
                creds = None

        if not refreshed:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            # This opens a browser once; after that, token.pickle is reused
            creds = flow.run_local_server(port=0)

        # Save the token
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return creds
