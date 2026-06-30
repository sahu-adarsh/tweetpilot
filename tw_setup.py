#!/usr/bin/env python3
"""
Run once to log in to X/Twitter and save the browser session.
After this, agent.py posts headlessly using the saved session.

Usage:
    python3 tw_setup.py
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

SESSION_FILE = Path(__file__).parent / "tw_session.json"


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://x.com/login")

        print("A browser window has opened.")
        print("Log in to X/Twitter, then come back here and press Enter...")
        input()

        await context.storage_state(path=str(SESSION_FILE))
        await browser.close()
        print(f"Session saved to {SESSION_FILE}")
        print("You can now run agent.py normally.")


asyncio.run(main())
