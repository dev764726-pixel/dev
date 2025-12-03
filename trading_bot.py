import logging
import time
import datetime
import pandas as pd
import pandas_ta as ta
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

class FlattradeTrader:
    def __init__(self):
        self.api = NorenApiPy(host='https://piconnect.flattrade.in/PiConnectTP/', websocket='wss://piconnect.flattrade.in/PiConnectWSTp/')
        self.session_active = False
        self.instrument_map = {}
        self.open_positions = {}
        self.buy_trades_today = 0
        self.sell_trades_today = 0

    def login(self):
        logging.info("Attempting to set API session...")
        if not config.user_id or not config.user_token or config.user_token == "PASTE_YOUR_DAILY_GENERATED_TOKEN_HERE":
            logging.error("User ID or User Token not set in config.py.")
            return False
        session_ok = self.api.set_session(userid=config.user_id, password="", usertoken=config.user_token)
        if session_ok:
            logging.info(f"Session set successfully for user: {config.user_id}")
            self.session_active = True
            self.start_websocket()
        else:
            logging.error("Failed to set session. Token might be incorrect or expired.")
            self.session_active = False
        return self.session_active

    def fetch_instrument_data(self):
        logging.info("Fetching instrument data for F&O symbols...")
        self.instrument_map = {}
        for symbol in config.FNO_SYMBOLS:
            try:
                ret = self.api.searchscrip(exchange='NSE', searchtext=symbol)
                if ret and ret.get('stat') == 'Ok' and ret.get('values'):
                    for val in ret['values']:
                        if val.get('tsym') == f"{symbol}-EQ":
                            self.instrument_map[symbol] = val
                            break
                time.sleep(0.4)
            except Exception as e:
                logging.warning(f"Could not find token for {symbol}: {e}")
        if not self.instrument_map:
            logging.error("Could not map any F&O symbols. Cannot proceed.")
            return False
        logging.info(f"Successfully mapped {len(self.instrument_map)} F&O symbols.")
        return True

    def run_strategy(self):
        logging.info("Strategy started. Waiting for Nifty check time...")
        while datetime.datetime.now().time() < datetime.time.fromisoformat(config.NIFTY_CHECK_TIME):
            time.sleep(1)

        market_direction, nifty_gain = self._get_nifty_market_direction()
        logging.info(f"Market direction determined: {market_direction} (Nifty Gain: {nifty_gain:.2%})")

        logging.info("Waiting for entry start time...")
        while datetime.datetime.now().time() < datetime.time.fromisoformat(config.ENTRY_START_TIME):
            time.sleep(1)

        self.evaluate_entry_conditions(market_direction)

        logging.info("Entry phase complete. Monitoring open positions until exit time.")
        while datetime.datetime.now().time() < datetime.time.fromisoformat(config.EXIT_TIME):
            time.sleep(5)

        logging.info("Exit time reached. Closing all open positions.")
        self.square_off_all_positions()
        self.logout()

    def _get_nifty_market_direction(self):
        try:
            exchange, token = config.NIFTY50_INDEX.split('|')
            quote = self.api.get_quotes(exchange=exchange, token=token)
            if not quote or quote.get('stat') != 'Ok':
                logging.error(f"Could not get Nifty 50 quote: {quote}")
                return 'Neutral', 0.0

            last_price = float(quote.get('lp', 0.0))
            prev_close = float(quote.get('c', 0.0))
            gain = (last_price - prev_close) / prev_close

            if gain > config.NIFTY_BULLISH_THRESHOLD: return 'Bullish', gain
            elif gain < config.NIFTY_BEARISH_THRESHOLD: return 'Bearish', gain
            else: return 'Neutral', gain
        except Exception as e:
            logging.error(f"Error checking Nifty 50 condition: {e}")
            return 'Neutral', 0.0

    def evaluate_entry_conditions(self, market_direction):
        logging.info("Starting to evaluate entry conditions for all F&O stocks.")
        symbols_to_check = list(self.instrument_map.keys())

        while datetime.datetime.now().time() < datetime.time.fromisoformat(config.EXIT_TIME):
            # Check if we can stop searching
            if (market_direction == 'Bullish' and self.buy_trades_today >= config.MAX_STOCKS_PER_LEG) or \
               (market_direction == 'Bearish' and self.sell_trades_today >= config.MAX_STOCKS_PER_LEG) or \
               (market_direction == 'Neutral' and self.buy_trades_today >= config.MAX_STOCKS_PER_LEG and self.sell_trades_today >= config.MAX_STOCKS_PER_LEG):
                logging.info("Reached max trades for all applicable legs. Stopping entry evaluation.")
                break

            for symbol in symbols_to_check:
                instrument = self.instrument_map[symbol]
                indicators = self._calculate_indicators(symbol, instrument['token'])
                if not indicators: continue

                # Bullish Market: Look for BUYS
                if market_direction == 'Bullish' and self.buy_trades_today < config.MAX_STOCKS_PER_LEG and self._check_buy_conditions(indicators):
                    self.place_trade(instrument, 'BUY', config.MAX_INVESTMENT_TRENDING)
                # Bearish Market: Look for SELLS
                elif market_direction == 'Bearish' and self.sell_trades_today < config.MAX_STOCKS_PER_LEG and self._check_sell_conditions(indicators):
                    self.place_trade(instrument, 'SELL', config.MAX_INVESTMENT_TRENDING)
                # Neutral Market: Look for both
                elif market_direction == 'Neutral':
                    if self.buy_trades_today < config.MAX_STOCKS_PER_LEG and self._check_buy_conditions(indicators):
                        self.place_trade(instrument, 'BUY', config.MAX_INVESTMENT_NEUTRAL)
                    if self.sell_trades_today < config.MAX_STOCKS_PER_LEG and self._check_sell_conditions(indicators):
                        self.place_trade(instrument, 'SELL', config.MAX_INVESTMENT_NEUTRAL)
                time.sleep(1)

    def _calculate_indicators(self, symbol, token):
        try:
            today = datetime.date.today()
            start_date = today - datetime.timedelta(days=45)
            ret = self.api.get_time_price_series(exchange='NSE', token=token, starttime=datetime.datetime.combine(start_date, datetime.time(9, 15)).timestamp(), interval=15)
            if not ret:
                logging.warning(f"{symbol}: Could not fetch 15-min data.")
                return None

            df = pd.DataFrame(ret)
            df['time'] = pd.to_datetime(df['time'], format='%d-%m-%Y %H:%M:%S')
            df.set_index('time', inplace=True)
            df = df.astype(float).iloc[::-1]

            # --- Volume Logic: SMA of first 15-min candle vs. today's first 15-min candle ---
            df_first_candle = df[df.index.time == datetime.time(9, 15)].copy()
            if len(df_first_candle) < 21:
                logging.warning(f"{symbol}: Not enough historical data for 20-day first candle volume SMA.")
                return None
            todays_first_candle_volume = df_first_candle['intv'].iloc[-1]
            volume_sma_20_days = df_first_candle['intv'].iloc[-21:-1].mean() # Avg of last 20 days, excluding today

            # --- Other Indicator Logic ---
            df.ta.rsi(length=config.RSI_PERIOD, append=True)
            df.ta.adx(length=config.ADX_PERIOD, append=True)
            df.ta.cci(length=config.CCI_PERIOD, append=True)
            latest = df.iloc[-1]

            # --- Daily Data Logic ---
            daily_ret = self.api.get_daily_price_series(exchange='NSE', tradingsymbol=f"{symbol}-EQ", startdate=start_date, enddate=today)
            if not daily_ret:
                logging.warning(f"{symbol}: Could not fetch daily data.")
                return None
            daily_df = pd.DataFrame(daily_ret).astype(float)

            return {
                'rsi': latest[f'RSI_{config.RSI_PERIOD}'], 'adx': latest[f'ADX_{config.ADX_PERIOD}'],
                'cci': latest[f'CCI_{config.CCI_PERIOD}_close'],
                'daily_volume': daily_df['v'].iloc[-1], 'daily_close': daily_df['c'].iloc[-1],
                'todays_first_candle_volume': todays_first_candle_volume,
                'volume_sma_20_days_first_candle': volume_sma_20_days
            }
        except Exception as e:
            logging.error(f"Error calculating indicators for {symbol}: {e}")
            return None

    def _check_buy_conditions(self, i):
        return (i['daily_volume'] > 500000 and 300 < i['daily_close'] < 10000 and i['rsi'] > 60 and i['adx'] > 45 and i['cci'] > -50 and i['todays_first_candle_volume'] > 2 * i['volume_sma_20_days_first_candle'])
    def _check_sell_conditions(self, i):
        return (i['daily_volume'] > 500000 and 300 < i['daily_close'] < 10000 and i['rsi'] < 40 and i['adx'] > 45 and i['cci'] < 50 and i['todays_first_candle_volume'] > 2 * i['volume_sma_20_days_first_candle'])

    def place_trade(self, instrument, trade_type, investment_amount):
        symbol = instrument['tsym'].replace('-EQ', '')
        if symbol in self.open_positions: return
        logging.info(f"Condition met for {symbol}. Placing {trade_type} trade.")
        try:
            quote = self.api.get_quotes(exchange='NSE', token=instrument['token'])
            price = float(quote.get('lp', 0.0))
            if price == 0: logging.error(f"Price for {symbol} is 0. Aborting."); return
            quantity = self._calculate_quantity(price, investment_amount)
            if quantity == 0: logging.warning(f"Quantity for {symbol} is 0. Aborting."); return

            ret = self.api.place_order(buy_or_sell=trade_type[0], product_type='I', exchange='NSE', tradingsymbol=instrument['tsym'], quantity=quantity, discloseqty=0, price_type='MKT', price=0.0, retention='DAY')
            if ret and ret.get('stat') == 'Ok':
                order_no = ret.get('norenordno')
                logging.info(f"Successfully placed {trade_type} order for {quantity} of {symbol}. Order No: {order_no}")
                pos = {'token': instrument['token'], 'quantity': quantity, 'type': trade_type, 'order_no': order_no, 'entry_price': price, 'status': 'OPEN'}
                pos['stop_loss'] = price * (1 - config.STOP_LOSS_PERCENT) if trade_type == 'BUY' else price * (1 + config.STOP_LOSS_PERCENT)
                pos['target'] = price * (1 + config.TAKE_PROFIT_PERCENT) if trade_type == 'BUY' else price * (1 - config.TAKE_PROFIT_PERCENT)
                pos['profit_locked'] = False
                self.open_positions[symbol] = pos
                if trade_type == 'BUY': self.buy_trades_today += 1
                else: self.sell_trades_today += 1
                self.api.subscribe(f"NSE|{instrument['token']}")
                logging.info(f"Subscribed to tick data for {symbol}.")
            else:
                logging.error(f"Failed to place order for {symbol}: {ret.get('emsg')}")
        except Exception as e:
            logging.error(f"Exception during trade placement for {symbol}: {e}")

    def _calculate_quantity(self, price, investment_amount):
        return int(investment_amount // price) if price > 0 else 0

    def handle_tick(self, tick_data):
        if 'tk' not in tick_data or 'lp' not in tick_data: return
        token, price = tick_data['tk'], float(tick_data['lp'])
        position = next((p for s, p in self.open_positions.items() if p['token'] == token), None)
        if not position or position['status'] != 'OPEN': return

        symbol = next((s for s, p in self.open_positions.items() if p['token'] == token), None)
        if not symbol: return

        # Target and SL checks
        if (position['type'] == 'BUY' and price >= position['target']) or (position['type'] == 'SELL' and price <= position['target']):
            logging.info(f"Take-profit hit for {symbol} at {price}. Squaring off.")
            self.square_off_position(symbol)
        elif (position['type'] == 'BUY' and price <= position['stop_loss']) or (position['type'] == 'SELL' and price >= position['stop_loss']):
            logging.warning(f"Stop-loss hit for {symbol} at {price}. Squaring off.")
            self.square_off_position(symbol)
        # "Lock Profit" logic
        else:
            if not position.get('profit_locked', False):
                profit_activation_price = position['entry_price'] * (1 + config.TRAILING_STOP_LOSS_ACTIVATE_PERCENT) if position['type'] == 'BUY' else position['entry_price'] * (1 - config.TRAILING_STOP_LOSS_ACTIVATE_PERCENT)

                if (position['type'] == 'BUY' and price >= profit_activation_price) or \
                   (position['type'] == 'SELL' and price <= profit_activation_price):

                    new_stop_loss = position['entry_price'] * (1 + config.TRAILING_STOP_LOSS_PERCENT) if position['type'] == 'BUY' else position['entry_price'] * (1 - config.TRAILING_STOP_LOSS_PERCENT)

                    # Ensure the new SL is better than the original one before updating
                    if (position['type'] == 'BUY' and new_stop_loss > position['stop_loss']) or \
                       (position['type'] == 'SELL' and new_stop_loss < position['stop_loss']):

                        position['stop_loss'] = new_stop_loss
                        position['profit_locked'] = True
                        logging.info(f"Profit locked for {symbol}. New Stop-Loss is {new_stop_loss:.2f}.")

    def handle_order_update(self, order):
        if order.get('status') == 'COMPLETE':
            symbol = order.get('tsym').replace('-EQ', '')
            if symbol in self.open_positions and self.open_positions[symbol]['order_no'] == order.get('norenordno'):
                self.open_positions[symbol]['entry_price'] = float(order.get('avgprc'))
                logging.info(f"Updated entry price for {symbol} to {self.open_positions[symbol]['entry_price']:.2f} based on execution.")

    def square_off_position(self, symbol):
        if symbol not in self.open_positions or self.open_positions[symbol]['status'] == 'CLOSED': return
        pos = self.open_positions[symbol]
        ret = self.api.place_order(buy_or_sell='S' if pos['type'] == 'BUY' else 'B', product_type='I', exchange='NSE', tradingsymbol=f"{symbol}-EQ", quantity=pos['quantity'], discloseqty=0, price_type='MKT', price=0.0)
        if ret and ret.get('stat') == 'Ok':
            logging.info(f"Successfully placed square-off order for {symbol}.")
            self.open_positions[symbol]['status'] = 'CLOSED'
        else:
            logging.error(f"Failed to square off {symbol}: {ret.get('emsg')}")

    def square_off_all_positions(self):
        logging.info("Squaring off all remaining open positions.")
        for symbol in list(self.open_positions.keys()):
            self.square_off_position(symbol)
            time.sleep(1)

    def start_websocket(self):
        if not self.session_active: logging.error("Cannot start websocket without active session."); return
        logging.info("Starting websocket...")
        self.api.start_websocket(order_update_callback=on_order_update, subscribe_callback=on_feed_update, socket_open_callback=on_socket_open, socket_close_callback=on_socket_close)
        while not feed_opened: time.sleep(1)

    def logout(self):
        if self.session_active:
            logging.info("Logging out...")
            self.api.logout()
        self.session_active = False

# Main execution block
if __name__ == "__main__":
    logging.basicConfig(level=config.LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(config.LOG_FILE), logging.StreamHandler()])
    logging.info("Trading Bot started.")
    bot = FlattradeTrader()
    if bot.login():
        if bot.fetch_instrument_data():
            bot.run_strategy()
        else:
            logging.error("Failed to initialize bot due to instrument data fetch error.")
    bot.logout()
    logging.info("Trading Bot finished.")
