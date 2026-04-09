from datetime import datetime, timedelta
import logging
import time
import random

import pandas as pd
import yfinance as yf

_log = logging.getLogger(__name__)


def get_stock_data_with_retry(ticker_symbol, start_date=None, end_date=None, interval='1d', max_retries=3):
    """Get stock data with short backoff retries (Yahoo rate limits)."""
    for attempt in range(max_retries):
        try:
            stock = yf.Ticker(ticker_symbol)
            if start_date and end_date:
                data = stock.history(start=start_date, end=end_date, interval=interval)
            else:
                data = stock.history(period="1d", interval=interval)
            if not data.empty:
                return data
        except Exception as e:
            _log.debug("yfinance attempt %s/%s failed for %s: %s", attempt + 1, max_retries, ticker_symbol, e)
            if attempt < max_retries - 1:
                time.sleep(random.uniform(0.2, 0.6))
            else:
                raise
    return pd.DataFrame()

'''Code for the data struture storing stock time series and analysis functions'''

class StockData:
    period_limit = 60 # 60 days for minute intervals 
    interval_set = set(["1m", "2m", "5m", "15m", "30m", "60m"])

    def __init__(self, stock_symbol, var1, var2=None, yf_interval='1d', allow_daily_fallback=True):
        """yf_interval applies when var2 is a YYYY-MM-DD end date (date-range fetch)."""
        self.ticker = stock_symbol
        if var2 is None:
            self.get_stock_data_for_date(stock_symbol, var1)
        elif len(var2) == 10:
            self.get_stock_data(stock_symbol, var1, var2, yf_interval, allow_daily_fallback)
        else:
            self.get_stock_data_for_time_interval(stock_symbol, var1, var2)

    # print error when no data is found
    def stock_error_message(self, stock_symbol, date):
        _log.warning("No Yahoo data for %s (requested around %s)", stock_symbol, date)

    # get stock data in a range (per day basis)
    def get_stock_data(self, stock_symbol, start_date, end_date, interval='1d', allow_daily_fallback=True):
        """Get stock data for a given symbol and date range.
        Args:
            stock_symbol: Stock ticker symbol (e.g., 'AAPL')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            interval: Data interval ('1d' for daily, '30m' for 30-minute)
        Returns:
            pandas.DataFrame: Stock data or empty DataFrame if no data found"""

        if start_date == end_date:
            _log.warning("StockData: start_date == end_date for %s", stock_symbol)

        _log.debug("Fetching %s %s %s → %s", interval, stock_symbol, start_date, end_date)
        self.stock_data = get_stock_data_with_retry(stock_symbol, start_date, end_date, interval)
        
        # Do not fall back to daily for minute/hour bars in sims: one daily row at midnight makes
        # minute-stepped currtime reuse the same bar every time (flat prices at 00:01, 00:02, ...).
        if self.stock_data.empty and interval in ['60m', '30m', '15m', '5m', '1m'] and allow_daily_fallback:
            _log.debug("No %s bars for %s; trying daily fallback", interval, stock_symbol)
            self.stock_data = get_stock_data_with_retry(stock_symbol, start_date, end_date, '1d')
        
        if self.stock_data.empty:
            self.stock_error_message(stock_symbol, start_date)
        else:
            self.stock_data.index = self.stock_data.index.tz_localize(None)
            self.curtime = self.stock_data.index[0]
        

    # get stock data (per day basis)
    def get_stock_data_for_date(self, stock_symbol, date):
        """Get stock data for a specific date.
        Args:
            stock_symbol: ticker symbol (e.g., 'AAPL')
            date: Date in 'YYYY-MM-DD' format
        Returns:
            pandas.DataFrame: Stock data for the specific date"""

        stock = yf.Ticker(stock_symbol)
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        new_date = date_obj + timedelta(days=1)
        self.stock_data = stock.history(start=date, end=new_date.strftime('%Y-%m-%d'))
        
        if self.stock_data.empty:
            self.stock_error_message(stock_symbol, date)
        else:
            self.stock_data.index = self.stock_data.index.tz_localize(None)

    # retrive stock data for minute time intervals 
    def get_stock_data_for_time_interval(self, stock_symbol, period, interval):
        """Get stock data for a specific time interval.
        Args:
            stock_symbol: ticker symbol (e.g., 'AAPL')
            period: period (e.g., '1d', '5d', '1mo')
            interval: interval (e.g., '1m', '5m', '15m', '30m', '60m')
        Returns:
            pandas.DataFrame: Stock data for the specific time interval"""
    
        if int(period[0:-1]) > self.period_limit and 'm' in interval:
            return "Error: Period cannot be greater than 60 days for minute intervals"
        elif interval not in self.interval_set:
            return "Error: Invalid interval"
        elif int(period[0:-1]) > 8 and interval == "1m":
            return "Error: Period cannot be greater than 8 days for 1-minute intervals"
    
        stock = yf.Ticker(stock_symbol)
        self.stock_data = stock.history(period=period, interval=interval)
        
        if self.stock_data.empty:
            self.stock_error_message(stock_symbol, period)
        else:
            self.stock_data.index = self.stock_data.index.tz_localize(None)
    
    def get_price(self):
        """
        Mark-to-market at self.curtime using the last bar with timestamp <= curtime (as-of).
        Avoids the old 'closest bar' logic, which could pick a *future* bar (lookahead bias) and
        misalign multi-ticker sims when bars don't line up to the second.
        """
        if getattr(self, 'stock_data', None) is None or getattr(self.stock_data, 'empty', True):
            return None

        ts = pd.Timestamp(self.curtime)
        df = self.stock_data
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()
            self.stock_data = df
        idx = df.index
        n = len(idx)
        if n == 0:
            return None

        typical_gap = idx[1] - idx[0] if n > 1 else timedelta(days=1)
        intraday = typical_gap <= timedelta(hours=1)
        max_stale = timedelta(hours=4) if intraday else timedelta(days=3)

        def _mid(row):
            return (float(row['High']) + float(row['Low'])) / 2.0

        pos = int(idx.searchsorted(ts, side='right')) - 1
        if pos >= 0:
            bar_t = pd.Timestamp(idx[pos])
            if ts >= bar_t and (ts - bar_t) <= pd.Timedelta(max_stale):
                return _mid(df.iloc[pos])

        if pos < 0 and n > 0:
            first_t = pd.Timestamp(idx[0])
            if first_t >= ts and (first_t - ts) <= pd.Timedelta(max_stale):
                return _mid(df.iloc[0])

        last_t = pd.Timestamp(idx[-1])
        if ts > last_t and (ts - last_t) <= pd.Timedelta(max_stale):
            return _mid(df.iloc[-1])

        _log.debug("No usable bar for %s at %s", self.ticker, ts)
        return None
    
    def moving_average(self, window='1h'):
        self.stock_data["SMA"] = self.stock_data['Close'].rolling(window=window).mean()
        return self.stock_data.loc[self.curtime, "SMA"]

    def price_increase(self):
        current_time = self.curtime
        start_time = self.stock_data.index[0]
        # Get the start price
        if start_time in self.stock_data.index:
            start_price = self.stock_data.loc[start_time, 'Close']
        else:
            # Find the closest available time to start_time
            available_times = self.stock_data.index
            if len(available_times) == 0:
                print("No data available for start time")
                return None
            
            # Find the closest time after or equal to start_time
            valid_times = available_times[available_times >= start_time]
            if len(valid_times) == 0:
                print(f"No data available after start time {start_time}")
                return None
            
            closest_start_time = valid_times[0]
            start_price = self.stock_data.loc[closest_start_time, 'Close']
        
        # Get the current price
        if current_time is None:
            # Use the latest available time
            current_price = self.stock_data['Close'].iloc[-1]
            current_time = self.stock_data.index[-1]
        else:
            if current_time in self.stock_data.index:
                current_price = self.stock_data.loc[current_time, 'Close']
            else:
                # Find the closest available time to current_time
                available_times = self.stock_data.index
                valid_times = available_times[available_times <= current_time]
                if len(valid_times) == 0:
                    print(f"No data available before current time {current_time}")
                    return None
                
                closest_current_time = valid_times[-1]
                current_price = self.stock_data.loc[closest_current_time, 'Close']
                current_time = closest_current_time
        
        # Calculate percentage change
        if start_price == 0:
            print("Start price is zero, cannot calculate percentage change")
            return None
        
        change_pct = (current_price - start_price) / start_price * 100
        
        return change_pct


def main():
    # Test with date range data
    df = StockData("AAPL", "2025-08-08", "2025-09-08")
    print(f"Stock: {df.ticker}")
    print(f"Data range: {df.stock_data.index[0]} to {df.stock_data.index[-1]}")
    # Test price increase with specific times
    df.curtime = datetime(2025, 8, 20)
    change = df.price_increase()
    print(change)
    print(df.moving_average())

if __name__ == "__main__":
    main()