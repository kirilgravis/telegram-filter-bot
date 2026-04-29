#!/usr/bin/env python3
"""
catch_up.py — Gap filler for the Telegram channel filter bot.

Fetches the last LOOK_BACK messages from the source channel, compares them
to what is already in the destination, and forwards any that are missing
and pass the filter — in chronological order (oldest first / FIFO).

Usage:
    python catch_up.py          # default: 300 messages
    python catch_up.py 500      # look back 500 messages
"""

import asyncio
import json
import logging
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

SOURCE_CHANNEL = config["source_channel"]
DESTINATION = config["destination"]
BLACKLIST = [w.lower() for w in config["blacklist"]]
WHITELIST = [w.lower() for w in config["whitelist"]]

DEFAULT_LOOK_BACK = 300

client = TelegramClient("session", API_ID, API_HASH)
bot = TelegramClient("bot_session", API_ID, API_HASH)


def should_skip(text: str) -> bool:
    text_lower = text.lower()
    has_blacklist = any(w in text_lower for w in BLACKLIST)
    has_whitelist = any(w in text_lower for w in WHITELIST)
    return has_blacklist and not has_whitelist


async def get_forwarded_source_ids(limit: int) -> set[int]:
    """Return set of source message IDs already present in the destination.

    channel_id is None due to Telegram forwarding privacy — we rely solely
    on channel_post (the original message ID) which is always present.
    Since the destination is a dedicated forwarding group, every fwd_from
    entry corresponds to the source channel.
    """
    forwarded = set()
    async for msg in client.iter_messages(DESTINATION, limit=limit):
        if msg.fwd_from and msg.fwd_from.channel_post is not None:
            forwarded.add(msg.fwd_from.channel_post)
    return forwarded


async def main(look_back: int = DEFAULT_LOOK_BACK) -> None:
    await client.start()
    log.info("User client connected.")
    await bot.start(bot_token=BOT_TOKEN)
    log.info("Bot client connected.")

    # ------------------------------------------------------------------
    # 1. Fetch last look_back messages from source, reverse to oldest-first
    # ------------------------------------------------------------------
    log.info("Fetching last %d messages from %s...", look_back, SOURCE_CHANNEL)
    source_msgs = []
    async for msg in client.iter_messages(SOURCE_CHANNEL, limit=look_back):
        source_msgs.append(msg)
    source_msgs.reverse()  # chronological (oldest first)
    log.info("Fetched %d source messages.", len(source_msgs))

    # ------------------------------------------------------------------
    # 2. Fetch already-forwarded message IDs from destination
    #    Use 3× look_back since many source messages are filtered out
    # ------------------------------------------------------------------
    dest_limit = look_back * 3
    log.info("Scanning up to %d destination messages for already-forwarded IDs...", dest_limit)
    already_forwarded = await get_forwarded_source_ids(dest_limit)
    log.info("Found %d already-forwarded source IDs in destination.", len(already_forwarded))

    # ------------------------------------------------------------------
    # 3. Group source messages into singles and albums, keep order
    # ------------------------------------------------------------------
    groups: dict[int, list] = {}
    singles: list = []
    for msg in source_msgs:
        if msg.grouped_id:
            groups.setdefault(msg.grouped_id, []).append(msg)
        else:
            singles.append(msg)

    items: list[tuple[int, str, object]] = []
    for msg in singles:
        items.append((msg.id, "single", msg))
    for album_msgs in groups.values():
        album_msgs.sort(key=lambda m: m.id)
        items.append((album_msgs[0].id, "album", album_msgs))
    items.sort(key=lambda x: x[0])  # chronological

    # ------------------------------------------------------------------
    # 4. Determine what to forward
    # ------------------------------------------------------------------
    to_forward = []
    skipped_already = 0
    skipped_blacklist = 0

    for _, kind, payload in items:
        if kind == "single":
            msg = payload
            if msg.id in already_forwarded:
                skipped_already += 1
                continue
            if should_skip(msg.message or ""):
                skipped_blacklist += 1
                log.info("Skipped message %d (blacklist)", msg.id)
                continue
            to_forward.append((kind, payload))
        else:
            album = payload
            # If the first part is already in destination, whole album was forwarded
            if album[0].id in already_forwarded:
                skipped_already += 1
                continue
            text = next((m.message for m in album if m.message), "")
            if should_skip(text):
                skipped_blacklist += 1
                log.info("Skipped album (first=%d, blacklist)", album[0].id)
                continue
            to_forward.append((kind, payload))

    log.info(
        "Summary — total: %d | already in destination: %d | blacklisted: %d | to forward: %d",
        len(items), skipped_already, skipped_blacklist, len(to_forward),
    )

    if not to_forward:
        log.info("All caught up — nothing to forward.")
        await client.disconnect()
        await bot.disconnect()
        return

    # ------------------------------------------------------------------
    # 5. Forward in FIFO order (oldest first)
    # ------------------------------------------------------------------
    forwarded_count = 0
    for kind, payload in to_forward:
        try:
            if kind == "single":
                log.info("Forwarding message %d via bot", payload.id)
                await bot.forward_messages(DESTINATION, payload.id, SOURCE_CHANNEL)
            else:
                ids = [m.id for m in payload]
                log.info("Forwarding album (%d items, first=%d) via bot", len(ids), ids[0])
                await bot.forward_messages(DESTINATION, ids, SOURCE_CHANNEL)
            forwarded_count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            if kind == "single":
                log.error("Failed to forward message %d: %s", payload.id, e)
            else:
                log.error("Failed to forward album (first=%d): %s", payload[0].id, e)

    log.info("Done. Forwarded %d item(s).", forwarded_count)

    await client.disconnect()
    await bot.disconnect()


if __name__ == "__main__":
    look_back = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOOK_BACK
    asyncio.run(main(look_back))
