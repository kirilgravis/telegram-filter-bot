#!/bin/bash
# run_always.sh — Process manager for the Always-Catch-Up script

# You can pass arguments to this script just like the python command:
# ./run_always.sh [mins] [amount]
# Default: 1 minute interval, 200 messages

INTERVAL=${1:-1}
AMOUNT=${2:-200}

while true; do
    echo "$(date) — Starting Always-Catch-Up (Interval: $INTERVAL min, Amount: $AMOUNT)..."
    python3 always_catch_up.py "$INTERVAL" "$AMOUNT"
    
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "$(date) — Bot stopped normally."
        break
    else
        echo "$(date) — Bot crashed with exit code $EXIT_CODE. Restarting in 10 seconds..."
        sleep 10
    fi
done
