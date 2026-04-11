# Telegram Channel Filter Bot

Monitors `@markettwits` and forwards messages to `@kg_capital_market`, filtering out messages that contain blacklisted hashtags (unless a whitelisted hashtag is also present).

## Setup

### 1. Get Telegram API credentials

1. Go to https://my.telegram.org
2. Log in with your phone number
3. Click **"API development tools"**
4. Create an app (any name/short name is fine)
5. Note your **api_id** (a number) and **api_hash** (a hex string)

### 2. Install dependencies

```bash
cd ~/Documents/Claude/telegram-filter-bot
pip install -r requirements.txt
```

### 3. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in your real values:

```
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890
```

### 4. Configure filter rules (optional)

Edit `config.json` to adjust:

- `source_channel` — the public channel to monitor
- `destination` — where to forward filtered messages
- `blacklist` — messages with these words (and no whitelist match) are skipped
- `whitelist` — these words override the blacklist

### 5. Run the bot

```bash
python main.py
```

**First run only:** Telethon will ask for your phone number and a verification code sent to your Telegram app. After authenticating, a `session.session` file is created so you won't need to log in again.

## Filter Logic

- Message contains a **blacklisted** word but NO **whitelisted** word → **skipped**
- Everything else → **forwarded** (including messages with no tags, or with both blacklist + whitelist tags)

## Stopping the bot

Press `Ctrl+C` in the terminal.
