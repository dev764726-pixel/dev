# Flattrade API Configuration

# --- Daily Credentials ---
# IMPORTANT: The user_token must be generated daily after 5:00 AM IST.
# Follow the instructions in the README to generate this token.
user_id = "YOUR_USER_ID_HERE"
user_token = "PASTE_YOUR_DAILY_GENERATED_TOKEN_HERE"


# --- Strategy Parameters ---
# Symbols & Indices
NIFTY50_INDEX = 'NSE|26000'  # Nifty 50 Index Instrument
NIFTY500_CSV_URL = 'https://archives.nseindia.com/content/indices/ind_nifty500list.csv'

# Time Settings
ENTRY_TIME = "09:20:00"
EXIT_TIME = "15:00:00"

# Strategy Thresholds
NIFTY_BULLISH_THRESHOLD = 0.0020  # +0.20% for long entry
NIFTY_BEARISH_THRESHOLD = -0.0020 # -0.20% for short entry
CANDLE_CROSS_THRESHOLD = 0.0002   # 0.02%
STOP_LOSS_PERCENT = 0.01          # 1% (absolute value)

# Order Settings
MAX_INVESTMENT_PER_STOCK = 20000
MAX_STOCKS_TO_TRADE = 5

# Logging
LOG_LEVEL = "INFO"  # Can be DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE = "trading_bot.log"