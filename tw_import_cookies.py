#!/usr/bin/env python3
"""
Import Twitter session cookies from your browser.
Run this instead of tw_setup.py when login is rate-limited.

Steps:
  1. Open Chrome and go to x.com (you must be logged in)
  2. Open DevTools: Cmd+Option+I
  3. Go to: Application → Cookies → https://x.com
  4. Find 'auth_token' → double-click its Value column → copy
  5. Find 'ct0'        → double-click its Value column → copy
  6. Paste each below when prompted
"""

import json
from pathlib import Path

SESSION_FILE = Path(__file__).parent / "tw_session.json"

print(__doc__)
auth_token = input("auth_token value: ").strip()
ct0 = input("ct0 value:        ").strip()

session = {
    "cookies": [
        {
            "name": "auth_token",
            "value": auth_token,
            "domain": ".x.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
        },
        {
            "name": "ct0",
            "value": ct0,
            "domain": ".x.com",
            "path": "/",
            "expires": -1,
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax",
        },
    ],
    "origins": [],
}

SESSION_FILE.write_text(json.dumps(session, indent=2))
print(f"\nSaved to {SESSION_FILE}")
print("You can now run agent.py (or test with the inline one-liner).")
