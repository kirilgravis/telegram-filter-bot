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

# User client — monitors the source channel (needs your personal account)
client = TelegramClient("session", API_ID, API_HASH)

# Bot client — forwards messages to destination (so you get notifications)
bot = TelegramClient("bot_session", API_ID, API_HASH)


def should_skip(text: str) -> bool:
    """Return True if the message should be filtered out.

    Skip only when the message contains a blacklisted word/tag
    AND does NOT contain any whitelisted word/tag.
    Everything else is forwarded.
    """
    text_lower = text.lower()
    has_blacklist = any(w in text_lower for w in BLACKLIST)
    has_whitelist = any(w in text_lower for w in WHITELIST)
    return has_blacklist and not has_whitelist


@client.on(events.Album(chats=SOURCE_CHANNEL))
async def album_handler(event):
    """Handle media groups (albums) — multiple photos/videos sent together."""
    text = ""
    for msg in event.messages:
        if msg.message:
            text = msg.message
            break

    if should_skip(text):
        log.info(
            "Skipped album (grouped_id=%s, %d items) — matched blacklist, no whitelist override",
            event.messages[0].grouped_id,
            len(event.messages),
        )
        return

    log.info("Forwarding album (%d items) to %s via bot", len(event.messages), DESTINATION)
    msg_ids = [msg.id for msg in event.messages]
    await bot.forward_messages(DESTINATION, msg_ids, SOURCE_CHANNEL)


@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def handler(event):
    # Skip messages that belong to an album — already handled by album_handler
    if event.message.grouped_id is not None:
        return

    text = event.message.message or ""
    if should_skip(text):
        log.info("Skipped message %s (matched blacklist, no whitelist override)", event.message.id)
        return

    log.info("Forwarding message %s to %s via bot", event.message.id, DESTINATION)
    await bot.forward_messages(DESTINATION, event.message.id, SOURCE_CHANNEL)


def main():
    log.info("Starting filter bot...")
    log.info("Source: %s | Destination: %s", SOURCE_CHANNEL, DESTINATION)
    log.info("Blacklist: %s | Whitelist: %s", BLACKLIST, WHITELIST)

    client.start()
    log.info("User client connected.")

    bot.start(bot_token=BOT_TOKEN)
    log.info("Bot client connected (@kg_forwarder_bot).")

    log.info("Listening for new messages...")
    client.run_until_disconnected()


if __name__ == "__main__":
    main()
