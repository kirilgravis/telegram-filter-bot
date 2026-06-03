#!/bin/bash
# run_bot.sh — Process manager for the Telegram bot

while true; do
    echo "$(date) — Starting Telegram Filter Bot..."
    python3 main.py
    echo "$(date) — Bot stopped or crashed with exit code $?. Restarting in 10 seconds..."
    sleep 10
done
