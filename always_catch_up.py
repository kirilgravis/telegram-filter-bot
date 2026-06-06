#!/usr/bin/env python3
"""
always_catch_up.py — Polling-based forwarder for the Telegram bot.

Runs the catch-up logic every X minutes, fetching the last Y messages.
Does NOT listen for real-time messages.

Usage:
    python always_catch_up.py [mins] [amount]
    python always_catch_up.py 1 200    # Every 1 min, look back 200 (default)
"""

import asyncio
import logging
import os
import sys
import time

from dotenv import load_dotenv
from telethon import TelegramClient
from catch_up import run_catch_up, API_ID, API_HASH, BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# Keep a small local cache of recently processed IDs to speed up checks
PROCESSED_IDS = set()

async def main():
    # Parse arguments
    try:
        interval_mins = int(sys.argv[1]) if len(sys.argv) > 1 else 1
        look_back = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    except ValueError:
        print("Usage: python always_catch_up.py [mins] [amount]")
        sys.exit(1)

    log.info("Starting Always-Catch-Up mode...")
    log.info("Interval: %d minute(s) | Look back: %d messages", interval_mins, look_back)

    client = TelegramClient("session", API_ID, API_HASH)
    bot = TelegramClient("bot_session", API_ID, API_HASH)

    await client.start()
    log.info("User client connected.")
    await bot.start(bot_token=BOT_TOKEN)
    log.info("Bot client connected.")

    try:
        while True:
            log.info("Running catch-up...")
            try:
                # Prune cache if it gets too large
                if len(PROCESSED_IDS) > 1000:
                    keep = sorted(list(PROCESSED_IDS))[-500:]
                    PROCESSED_IDS.clear()
                    PROCESSED_IDS.update(keep)

                await run_catch_up(client, bot, look_back, processed_ids=PROCESSED_IDS)
            except Exception as e:
                log.exception("Error during catch-up: %s", e)

            log.info("Done. Sleeping for %d minute(s)...", interval_mins)
            await asyncio.sleep(interval_mins * 60)
    except KeyboardInterrupt:
        log.info("Stopping...")
    finally:
        await client.disconnect()
        await bot.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
