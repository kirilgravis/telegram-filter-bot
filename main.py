import json
import os
import logging
import asyncio

from dotenv import load_dotenv
from telethon import TelegramClient, events
from catch_up import run_catch_up

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

# Track recently processed source message IDs to prevent duplicates
PROCESSED_IDS = set()


def should_skip(text: str) -> bool:
    """Return True if the message should be filtered out."""
    text_lower = text.lower()
    has_blacklist = any(w in text_lower for w in BLACKLIST)
    has_whitelist = any(w in text_lower for w in WHITELIST)
    return has_blacklist and not has_whitelist


async def scheduled_catch_up(client, bot, lock):
    """Run catch_up logic every 30 minutes."""
    while True:
        if len(PROCESSED_IDS) > 1000:
            keep = sorted(list(PROCESSED_IDS))[-500:]
            PROCESSED_IDS.clear()
            PROCESSED_IDS.update(keep)

        log.info("Starting periodic catch-up (look_back=200)...")
        try:
            await run_catch_up(client, bot, 200, processed_ids=PROCESSED_IDS, lock=lock)
        except Exception as e:
            log.exception("Error during periodic catch-up: %s", e)
        
        log.info("Catch-up finished. Next run in 30 minutes.")
        await asyncio.sleep(30 * 60)


async def main():
    log.info("Starting filter bot...")

    # Initialize inside main() to ensure loop-binding is fresh on every restart
    client = TelegramClient("session", API_ID, API_HASH)
    bot = TelegramClient("bot_session", API_ID, API_HASH)
    forward_lock = asyncio.Lock()

    @client.on(events.Album(chats=SOURCE_CHANNEL))
    async def album_handler(event):
        text = ""
        for msg in event.messages:
            if msg.message:
                text = msg.message
                break

        if should_skip(text):
            log.info("Skipped album %s (blacklist)", event.messages[0].grouped_id)
            return

        if any(msg.id in PROCESSED_IDS for msg in event.messages):
            return

        log.info("Forwarding album (%d items) to %s via bot", len(event.messages), DESTINATION)
        msg_ids = [msg.id for msg in event.messages]
        
        async with forward_lock:
            await bot.forward_messages(DESTINATION, msg_ids, SOURCE_CHANNEL)
            await asyncio.sleep(1)
        
        for mid in msg_ids:
            PROCESSED_IDS.add(mid)

    @client.on(events.NewMessage(chats=SOURCE_CHANNEL))
    async def handler(event):
        if event.message.grouped_id is not None or event.message.id in PROCESSED_IDS:
            return

        text = event.message.message or ""
        if should_skip(text):
            # log.info("Skipped message %s (blacklist)", event.message.id)
            return

        log.info("Forwarding message %s to %s via bot", event.message.id, DESTINATION)
        
        async with forward_lock:
            await bot.forward_messages(DESTINATION, event.message.id, SOURCE_CHANNEL)
            await asyncio.sleep(1)
            
        PROCESSED_IDS.add(event.message.id)

    await client.start()
    await bot.start(bot_token=BOT_TOKEN)
    log.info("Connected and listening...")

    asyncio.create_task(scheduled_catch_up(client, bot, forward_lock))
    await client.run_until_disconnected()


if __name__ == "__main__":
    import time
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            break
        except Exception:
            log.exception("Bot crashed! Restarting in 10 seconds...")
            time.sleep(10)
