import logging
import time
import datetime
import csv
import requests
import io
import config
from NorenRestApiPy.NorenApi import NorenApi as NorenApiPy

# Global variable to manage websocket state
feed_opened = False

# --- Callback Functions for Websocket ---
def on_feed_update(tick_data):
    """Callback for receiving price ticks."""
    logging.debug(f"Feed update: {tick_data}")
    if 'bot' in globals() and bot.session_active:
        bot.handle_tick(tick_data)

def on_order_update(order_data):
    """Callback for receiving order updates."""
    logging.info(f"Order update: {order_data}")
    if 'bot' in globals() and bot.session_active:
        bot.handle_order_update(order_data)

def on_socket_open():
    """Callback for when the websocket connection is established."""
    global feed_opened
    feed_opened = True
    logging.info("Websocket connection opened.")

def on_socket_close():
    """Callback for when the websocket connection is closed."""
    global feed_opened
    feed_opened = False
    logging.warning("Websocket connection closed.")

class ShoonyaTrader:
    """
    The main class to handle API interactions, websocket connection,
    and trading logic.
    """
    def __init__(self):
        self.api = ShoonyaApiPy()
        self.session_active = False
        self.nse_instruments = None
        self.nifty500_symbols = None
        self.open_positions = {}
        self.traded_stocks = set()
        self.instrument_map = {}

    def run_strategy(self):
        """The main loop that drives the trading strategy."""
        logging.info("Strategy started. Waiting for 09:20 AM.")
        while datetime.datetime.now().time() < datetime.time.fromisoformat(config.ENTRY_TIME):
            time.sleep(1)

        logging.info("It's 09:20 AM. Starting entry condition checks.")
        self.evaluate_entry_conditions()

        logging.info("Entry phase complete. Monitoring open positions.")
        while datetime.datetime.now().time() < datetime.time.fromisoformat(config.EXIT_TIME):
            time.sleep(1)

        logging.info("It's 03:00 PM. Closing all open positions.")
        self.square_off_all_positions()
        self.logout()

    def evaluate_entry_conditions(self):
        """Determines market direction and triggers trading logic."""
        logging.info("Evaluating market direction...")
        market_direction, nifty_gain = self._get_nifty_market_direction()

        if market_direction == 'Bullish':
            logging.info(f"Market is Bullish (Nifty gain: {nifty_gain:.2%}). Searching for long candidates.")
            candidates = self._find_top_nifty500_gainers()
            if candidates:
                logging.info(f"Found top gainers for long trades: {[c['tsym'] for c in candidates]}")
                self._process_trades(candidates, 'BUY')
        elif market_direction == 'Bearish':
            logging.info(f"Market is Bearish (Nifty gain: {nifty_gain:.2%}). Searching for short candidates.")
            candidates = self._find_top_nifty500_gainers() # Using top gainers as per user spec
            if candidates:
                logging.info(f"Found top gainers for short trades: {[c['tsym'] for c in candidates]}")
                self._process_trades(candidates, 'SELL')
        else:
            logging.warning(f"Market is Neutral (Nifty gain: {nifty_gain:.2%}). No trades initiated.")

    def _process_trades(self, candidates, trade_type):
        """Iterates through candidates and checks for entry conditions."""
        for candidate in candidates:
            if len(self.open_positions) >= config.MAX_STOCKS_TO_TRADE:
                logging.info("Reached max number of trades. Stopping.")
                break
            if candidate['tsym'] in self.traded_stocks:
                logging.debug(f"Already traded {candidate['tsym']} today. Skipping.")
                continue

            logging.info(f"Checking {trade_type} conditions for {candidate['tsym']}...")
            entry_condition_met = False
            if trade_type == 'BUY':
                entry_condition_met = self._check_stock_buy_conditions(candidate['token'])
            else: # SELL
                entry_condition_met = self._check_stock_sell_conditions(candidate['token'])

            if entry_condition_met:
                logging.info(f"{trade_type} entry conditions met for {candidate['tsym']}.")
                self.place_trade(candidate, trade_type)
            else:
                logging.info(f"Entry conditions for {candidate['tsym']} not met.")
            time.sleep(1)

    def _get_nifty_market_direction(self):
        """Determines market direction. Returns ('Bullish'/'Bearish'/'Neutral', gain_%)."""
        try:
            exchange, token = config.NIFTY50_INDEX.split('|')
            quote = self.api.get_quotes(exchange=exchange, token=token)
            if not quote or quote.get('stat') != 'Ok':
                logging.error(f"Could not get Nifty 50 quote: {quote}")
                return 'Neutral', 0.0

            last_price = float(quote.get('lp', 0.0))
            prev_close = float(quote.get('c', 0.0))
            if prev_close == 0:
                logging.error("Nifty 50 previous close is 0.")
                return 'Neutral', 0.0

            gain = (last_price - prev_close) / prev_close
            if gain > config.NIFTY_BULLISH_THRESHOLD:
                return 'Bullish', gain
            elif gain < config.NIFTY_BEARISH_THRESHOLD:
                return 'Bearish', gain
            else:
                return 'Neutral', gain
        except Exception as e:
            logging.error(f"Error checking Nifty 50 condition: {e}")
            return 'Neutral', 0.0

    def _check_stock_buy_conditions(self, token):
        """Checks candle conditions for a BUY trade."""
        try:
            today = datetime.date.today()
            start_time = datetime.datetime.combine(today, datetime.time(9, 15))
            end_time = datetime.datetime.combine(today, datetime.time(9, 25))

            ret = self.api.get_time_price_series(
                exchange='NSE',
                token=token,
                starttime=start_time.timestamp(),
                endtime=end_time.timestamp(),
                interval=5
            )

            if not ret or len(ret) < 2:
                logging.warning(f"Could not fetch sufficient 5-min candle data for token {token}.")
                return False

            second_candle = ret[0]
            first_candle = ret[1]

            first_candle_open = float(first_candle.get('into'))
            first_candle_close = float(first_candle.get('intc'))
            second_candle_high = float(second_candle.get('inth'))

            if first_candle_close <= first_candle_open:
                logging.debug(f"Token {token}: First candle was not green.")
                return False

            entry_price_target = first_candle_close * (1 + config.CANDLE_CROSS_THRESHOLD)
            if second_candle_high <= entry_price_target:
                logging.debug(f"Token {token}: High did not cross target.")
                return False

            logging.info(f"Token {token}: All BUY conditions met.")
            return True

        except Exception as e:
            logging.error(f"An error occurred checking stock BUY conditions for token {token}: {e}")
            return False

    def _check_stock_sell_conditions(self, token):
        """Checks candle conditions for a SELL trade."""
        try:
            today = datetime.date.today()
            start_time = datetime.datetime.combine(today, datetime.time(9, 15))
            end_time = datetime.datetime.combine(today, datetime.time(9, 25))

            ret = self.api.get_time_price_series(
                exchange='NSE',
                token=token,
                starttime=start_time.timestamp(),
                endtime=end_time.timestamp(),
                interval=5
            )

            if not ret or len(ret) < 2:
                logging.warning(f"Could not fetch sufficient 5-min candle data for token {token}.")
                return False

            second_candle = ret[0]
            first_candle = ret[1]

            first_candle_open = float(first_candle.get('into'))
            first_candle_close = float(first_candle.get('intc'))
            second_candle_low = float(second_candle.get('intl'))

            # Condition 1: First candle must be red
            if first_candle_close >= first_candle_open:
                logging.debug(f"Token {token}: First candle was not red.")
                return False

            # Condition 2: Low of second candle must cross below threshold
            entry_price_target = first_candle_close * (1 - config.CANDLE_CROSS_THRESHOLD)
            if second_candle_low >= entry_price_target:
                logging.debug(f"Token {token}: Low did not cross target.")
                return False

            logging.info(f"Token {token}: All SELL conditions met.")
            return True

        except Exception as e:
            logging.error(f"An error occurred checking stock SELL conditions for token {token}: {e}")
            return False

    def handle_tick(self, tick_data):
        """Processes real-time price ticks to monitor stop-losses."""
        if not tick_data or 'tk' not in tick_data or 'lp' not in tick_data:
            return

        token = tick_data['tk']
        last_price = float(tick_data['lp'])

        position_to_check = None
        for tsym, pos_details in self.open_positions.items():
            if pos_details['token'] == token:
                position_to_check = tsym
                break

        if position_to_check:
            position = self.open_positions[position_to_check]

            # Check stop loss for both long and short positions
            if position['type'] == 'BUY' and last_price <= position['stop_loss']:
                logging.warning(f"Stop-loss triggered for LONG position {position_to_check} at price {last_price}.")
                self.square_off_position(position_to_check)
            elif position['type'] == 'SELL' and last_price >= position['stop_loss']:
                logging.warning(f"Stop-loss triggered for SHORT position {position_to_check} at price {last_price}.")
                self.square_off_position(position_to_check)

    def handle_order_update(self, order_data):
        """Updates position details based on order execution updates."""
        if order_data.get('status') == 'COMPLETE':
            tsym = order_data.get('tsym')
            if tsym in self.open_positions and self.open_positions[tsym]['order_no'] == order_data.get('norenordno'):
                avg_price = float(order_data.get('avgprc'))
                pos_type = self.open_positions[tsym]['type']

                self.open_positions[tsym]['entry_price'] = avg_price
                if pos_type == 'BUY':
                    self.open_positions[tsym]['stop_loss'] = avg_price * (1 - config.STOP_LOSS_PERCENT)
                else: # SELL
                    self.open_positions[tsym]['stop_loss'] = avg_price * (1 + config.STOP_LOSS_PERCENT)

                logging.info(f"Updated entry price for {tsym} to {avg_price:.2f} and SL to {self.open_positions[tsym]['stop_loss']:.2f}.")

    def square_off_position(self, symbol):
        """Places an order to close an open position."""
        if symbol not in self.open_positions:
            return

        pos = self.open_positions[symbol]
        square_off_action = 'S' if pos['type'] == 'BUY' else 'B'

        logging.info(f"Squaring off {pos['quantity']} shares of {symbol}.")
        ret = self.api.place_order(
            buy_or_sell=square_off_action,
            product_type='I',
            exchange='NSE',
            tradingsymbol=symbol,
            quantity=pos['quantity'],
            discloseqty=0,
            price_type='MKT',
            price=0.0,
            retention='DAY'
        )

        if ret and ret.get('stat') == 'Ok':
            logging.info(f"Successfully placed square-off order for {symbol}.")
            del self.open_positions[symbol]
        else:
            logging.error(f"Failed to place square-off order for {symbol}. Reason: {ret.get('emsg')}")

    def square_off_all_positions(self):
        """Iterates through all open positions and squares them off."""
        logging.info("Squaring off all remaining open positions.")
        for symbol in list(self.open_positions.keys()):
            self.square_off_position(symbol)
            time.sleep(1)

    def place_trade(self, instrument, trade_type):
        """Calculates quantity and places a market order."""
        try:
            quote = self.api.get_quotes(exchange='NSE', token=instrument['token'])
            last_price = float(quote.get('lp', 0.0))
            if last_price == 0:
                logging.error(f"Last price is 0 for {instrument['tsym']}. Aborting trade.")
                return

            quantity = self._calculate_quantity(last_price)
            if quantity == 0:
                logging.warning(f"Calculated quantity is 0 for {instrument['tsym']}. Aborting trade.")
                return

            logging.info(f"Placing {trade_type} order for {quantity} shares of {instrument['tsym']}.")
            ret = self.api.place_order(
                buy_or_sell=trade_type[0], # 'B' or 'S'
                product_type='I',
                exchange='NSE',
                tradingsymbol=instrument['tsym'],
                quantity=quantity,
                discloseqty=0,
                price_type='MKT',
                price=0.0,
                retention='DAY'
            )

            if ret and ret.get('stat') == 'Ok':
                order_no = ret.get('norenordno')
                logging.info(f"Successfully placed {trade_type} order for {instrument['tsym']}. Order no: {order_no}")

                sl_price = 0
                if trade_type == 'BUY':
                    sl_price = last_price * (1 - config.STOP_LOSS_PERCENT)
                else: # SELL
                    sl_price = last_price * (1 + config.STOP_LOSS_PERCENT)

                self.open_positions[instrument['tsym']] = {
                    'token': instrument['token'],
                    'quantity': quantity,
                    'entry_price': last_price, # Approximate, will be updated
                    'stop_loss': sl_price,
                    'order_no': order_no,
                    'type': trade_type
                }
                self.traded_stocks.add(instrument['tsym'])
                self.api.subscribe(f"NSE|{instrument['token']}")
                logging.info(f"Subscribed to tick data for {instrument['tsym']}.")
            else:
                logging.error(f"Failed to place order for {instrument['tsym']}. Reason: {ret.get('emsg')}")

        except Exception as e:
            logging.error(f"Exception during trade placement for {instrument['tsym']}: {e}")

    def _calculate_quantity(self, price):
        """Calculates order quantity."""
        if price == 0: return 0
        return int(config.MAX_INVESTMENT_PER_STOCK // price)

    def _find_top_nifty500_gainers(self):
        """Finds the top 5 gaining stocks from the Nifty 500 list."""
        logging.info(f"Calculating gains for {len(self.instrument_map)} mapped Nifty 500 stocks.")
        gainers = []
        for symbol, instrument_data in self.instrument_map.items():
            try:
                quote = self.api.get_quotes(exchange='NSE', token=instrument_data['token'])
                if quote and quote.get('stat') == 'Ok':
                    last_price = float(quote.get('lp', 0.0))
                    prev_close = float(quote.get('c', 0.0))
                    if prev_close > 0:
                        gain = (last_price - prev_close) / prev_close
                        gainers.append({
                            'tsym': instrument_data['tsym'],
                            'token': instrument_data['token'],
                            'gain': gain
                        })
            except Exception as e:
                logging.warning(f"Could not fetch quote for {symbol}: {e}")
                continue
            time.sleep(0.4) # Avoid API rate limit

        if not gainers:
            logging.error("Could not calculate gains for any Nifty 500 stock.")
            return []

        sorted_gainers = sorted(gainers, key=lambda x: x['gain'], reverse=True)
        return sorted_gainers[:config.MAX_STOCKS_TO_TRADE]

    def login(self):
        """Authenticate with the Flattrade API using the daily token."""
        logging.info("Attempting to set API session...")
        if not config.user_id or not config.user_token or config.user_token == "PASTE_YOUR_DAILY_GENERATED_TOKEN_HERE":
            logging.error("User ID or User Token is not set in config.py. Please generate a token for today.")
            return False

        try:
            ret = self.api.set_session(userid=config.user_id, password="", usertoken=config.user_token)
            if ret and ret.get('stat') == 'Ok':
                logging.info(f"Session set successfully for user: {ret.get('uname')}")
                self.session_active = True
                self.start_websocket()
            else:
                logging.error(f"Failed to set session: {ret.get('emsg')}")
                self.session_active = False
        except Exception as e:
            logging.error(f"An exception occurred during session setup: {e}")
            self.session_active = False
        return self.session_active

    def fetch_instrument_data(self):
        """
        Downloads the Nifty 500 list and then finds the instrument token
        for each stock individually using the searchscrip API call.
        """
        logging.info("Fetching Nifty 500 instrument data...")
        try:
            # 1. Get Nifty 500 constituents using the csv module
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(config.NIFTY500_CSV_URL, headers=headers)
            response.raise_for_status()

            # Use the csv module to read the data
            csv_file = io.StringIO(response.text)
            reader = csv.DictReader(csv_file)
            self.nifty500_symbols = {row['Symbol'] for row in reader}
            logging.info(f"Successfully fetched {len(self.nifty500_symbols)} Nifty 500 symbol names.")

            # 2. Iteratively find the token for each symbol
            logging.info("Searching for instrument tokens for Nifty 500 stocks. This will take a few minutes...")
            self.instrument_map = {}
            for symbol in self.nifty500_symbols:
                try:
                    # Search for the equity instrument
                    ret = self.api.searchscrip(exchange='NSE', searchtext=f'{symbol}')
                    if ret and ret.get('stat') == 'Ok' and ret.get('values'):
                        for val in ret['values']:
                            # Ensure we get the equity segment, not derivatives
                            if val.get('tsym', '').endswith('-EQ'):
                                self.instrument_map[symbol] = val
                                break
                    time.sleep(0.4) # To avoid API rate limiting
                except Exception as e:
                    logging.warning(f"Could not find token for {symbol}: {e}")

            if not self.instrument_map:
                logging.error("Could not map any Nifty 500 symbols to instrument tokens. Cannot proceed.")
                return False

            logging.info(f"Successfully mapped {len(self.instrument_map)} Nifty 500 symbols to tokens.")
            return True

        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to download Nifty 500 list: {e}")
            return False
        except Exception as e:
            logging.error(f"An unexpected error occurred during instrument data fetching: {e}")
            return False

    def start_websocket(self):
        """Initializes and starts the websocket connection."""
        if not self.session_active:
            logging.error("Cannot start websocket without an active session.")
            return

        logging.info("Starting websocket...")
        self.api.start_websocket(
            order_update_callback=on_order_update,
            subscribe_callback=on_feed_update,
            socket_open_callback=on_socket_open,
            socket_close_callback=on_socket_close
        )
        while not feed_opened:
            logging.debug("Waiting for websocket to open...")
            time.sleep(1)

    def logout(self):
        """Logs out from the API session."""
        if self.session_active:
            logging.info("Logging out...")
            ret = self.api.logout()
            if ret and ret.get('stat') == 'Ok':
                logging.info("Logout successful.")
            else:
                logging.error(f"Logout failed: {ret.get('emsg')}")
        self.session_active = False


# Main execution block
if __name__ == "__main__":
    logging.basicConfig(level=config.LOG_LEVEL,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[
                            logging.FileHandler(config.LOG_FILE),
                            logging.StreamHandler()
                        ])
    logging.info("Trading Bot started.")

    bot = ShoonyaTrader()
    if bot.login():
        if bot.fetch_instrument_data():
            bot.run_strategy()
        else:
            logging.error("Failed to initialize bot due to instrument data fetch error.")
            bot.logout()

    logging.info("Trading Bot finished.")