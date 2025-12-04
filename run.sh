#!/bin/bash
# This script ensures the trading bot is run with the correct Python interpreter from the activated virtual environment.

# Find the python executable in the current environment's PATH
PYTHON_EXEC=$(which python)

echo "Using Python interpreter at: $PYTHON_EXEC"
echo "Starting the trading bot..."
echo ""

# Run the bot with the found interpreter
$PYTHON_EXEC trading_bot.py
