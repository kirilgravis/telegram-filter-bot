import asyncio
import json
import os
import logging

from dotenv import load_dotenv
from telethon import TelegramClient, events

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

STATE_FILE = "state.json"

# User client — monitors the source channel (needs your personal account)
client = TelegramClient("session", API_ID, API_HASH)

# Bot client — forwards messages to destination (so you get notifications)
bot = TelegramClient("bot_session", API_ID, API_HASH)

# In-memory dedup set for this session (belt-and-suspenders with state.json)
_session_processed: set[int] = set()


# ---------------------------------------------------------------------------
# State persistence — so we don't re-forward messages across restarts
# ---------------------------------------------------------------------------

def load_last_id() -> int:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return int(json.load(f).get("last_processed_id", 0))
        except (json.JSONDecodeError, ValueError):
            return 0
    return 0


def save_last_id(msg_id: int) -> None:
    """Only advance — never move backward."""
    current = load_last_id()
    if msg_id > current:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_processed_id": msg_id}, f)


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

def should_skip(text: str) -> bool:
    """Skip only when the message contains a blacklisted word AND no whitelisted word."""
    text_lower = text.lower()
    has_blacklist = any(w in text_lower for w in BLACKLIST)
    has_whitelist = any(w in text_lower for w in WHITELIST)
    return has_blacklist and not has_whitelist


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

async def process_single(msg) -> None:
    if msg.id in _session_processed or msg.id <= load_last_id():
        return
    _session_processed.add(msg.id)

    text = msg.message or ""
    if should_skip(text):
        log.info("Skipped message %d (blacklist, no whitelist override)", msg.id)
    else:
        log.info("Forwarding message %d via bot", msg.id)
        await bot.forward_messages(DESTINATION, msg.id, SOURCE_CHANNEL)
    save_last_id(msg.id)


async def process_album(msgs) -> None:
    max_id = max(m.id for m in msgs)
    if max_id <= load_last_id() or any(m.id in _session_processed for m in msgs):
        return
    for m in msgs:
        _session_processed.add(m.id)

    text = ""
    for m in msgs:
        if m.message:
            text = m.message
            break

    if should_skip(text):
        log.info(
            "Skipped album (grouped_id=%s, %d items)",
            msgs[0].grouped_id, len(msgs),
        )
    else:
        log.info("Forwarding album (%d items) via bot", len(msgs))
        ids = [m.id for m in msgs]
        await bot.forward_messages(DESTINATION, ids, SOURCE_CHANNEL)
    save_last_id(max_id)


# ---------------------------------------------------------------------------
# Catch-up on startup
# ---------------------------------------------------------------------------

async def catch_up() -> None:
    last_id = load_last_id()

    if last_id == 0:
        # First run — set a baseline so we don't replay the entire channel history
        log.info("First run: setting baseline (will process messages posted from now on).")
        async for msg in client.iter_messages(SOURCE_CHANNEL, limit=1):
            save_last_id(msg.id)
            log.info("Baseline set at message ID %d.", msg.id)
            return
        log.info("Source channel has no messages yet.")
        return

    log.info("Catching up from message ID %d...", last_id)

    # Fetch all messages newer than last_id, oldest first
    messages = []
    async for msg in client.iter_messages(SOURCE_CHANNEL, min_id=last_id, reverse=True):
        messages.append(msg)

    if not messages:
        log.info("Nothing to catch up on.")
        return

    log.info("Found %d missed message(s). Processing...", len(messages))

    # Group by grouped_id so albums process as one unit
    groups: dict[int, list] = {}
    singles: list = []
    for msg in messages:
        if msg.grouped_id:
            groups.setdefault(msg.grouped_id, []).append(msg)
        else:
            singles.append(msg)

    # Build an ordered list of work items (by first message ID)
    items = []
    for msg in singles:
        items.append((msg.id, "single", msg))
    for msgs in groups.values():
        msgs.sort(key=lambda m: m.id)
        items.append((msgs[0].id, "album", msgs))
    items.sort(key=lambda x: x[0])

    for _, kind, payload in items:
        try:
            if kind == "single":
                await process_single(payload)
            else:
                await process_album(payload)
            await asyncio.sleep(0.5)  # gentle pacing to stay under rate limits
        except Exception as e:
            log.error("Error processing during catch-up: %s", e)

    log.info("Catch-up complete.")


# ---------------------------------------------------------------------------
# Live event handlers
# ---------------------------------------------------------------------------

@client.on(events.Album(chats=SOURCE_CHANNEL))
async def album_handler(event):
    await process_album(event.messages)


@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def new_message_handler(event):
    if event.message.grouped_id is not None:
        return  # album parts handled by album_handler
    await process_single(event.message)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    log.info("Starting filter bot...")
    log.info("Source: %s | Destination: %s", SOURCE_CHANNEL, DESTINATION)
    log.info("Blacklist: %s | Whitelist: %s", BLACKLIST, WHITELIST)

    await client.start()
    log.info("User client connected.")

    await bot.start(bot_token=BOT_TOKEN)
    log.info("Bot client connected.")

    await catch_up()

    log.info("Listening for new messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
