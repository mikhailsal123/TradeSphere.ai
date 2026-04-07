from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf


def get_stock_data_with_retry(ticker_symbol, start_date=None, end_date=None, interval='1d', max_retries=3):
    """Get stock data with retry logic and delays to avoid rate limiting"""
    import time
    import random
    
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
            print(f"DEBUG: Attempt {attempt + 1} failed for {ticker_symbol}: {str(e)}")
            if attempt < max_retries - 1:
                delay = random.uniform(1, 3)  # Random delay between 1-3 seconds
                print(f"DEBUG: Waiting {delay:.1f} seconds before retry...")
                time.sleep(delay)
            else:
                raise e
    
    return pd.DataFrame()  # Return empty DataFrame if all retries fail

'''Code for the data struture storing stock time series and analysis functions'''

class StockData:
    period_limit = 60 # 60 days for minute intervals 
    interval_set = set(["1m", "2m", "5m", "15m", "30m", "60m"])

    def __init__(self, stock_symbol, var1, var2 = None): # var1 and var2 define which 
        self.ticker = stock_symbol
        if var2 is None:
            self.get_stock_data_for_date(stock_symbol, var1)
        #date format length
        elif len(var2) == 10:
            self.get_stock_data(stock_symbol, var1, var2)
        else:
            self.get_stock_data_for_time_interval(stock_symbol, var1, var2)

    # print error when no data is found
    def stock_error_message(self, stock_symbol, date):
        print(f"${stock_symbol}: No data found for {date}")
        print("This might be because:")
        print("- The date falls on a weekend or holiday")
        print("- The stock symbol is invalid")

    # get stock data in a range (per day basis)
    def get_stock_data(self, stock_symbol, start_date, end_date, interval='1d'):
        """Get stock data for a given symbol and date range.
        Args:
            stock_symbol: Stock ticker symbol (e.g., 'AAPL')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            interval: Data interval ('1d' for daily, '30m' for 30-minute)
        Returns:
            pandas.DataFrame: Stock data or empty DataFrame if no data found"""

        if start_date == end_date:
            print("Error: End date is the same as start date")
    
        print(f"DEBUG: Fetching {interval} data for {stock_symbol} from {start_date} to {end_date}")
        self.stock_data = get_stock_data_with_retry(stock_symbol, start_date, end_date, interval)
        
        # If no data for intraday interval, try daily data as fallback
        if self.stock_data.empty and interval in ['60m', '30m', '15m', '5m', '1m']:
            print(f"DEBUG: No {interval} data available, trying daily data as fallback")
            self.stock_data = get_stock_data_with_retry(stock_symbol, start_date, end_date, '1d')
            if not self.stock_data.empty:
                print(f"DEBUG: Got {len(self.stock_data)} daily data points as fallback for {stock_symbol}")
        
        if self.stock_data.empty:
            print(f"DEBUG: No data returned for {stock_symbol} with interval {interval}")
            self.stock_error_message(stock_symbol, start_date)
        else:
            print(f"DEBUG: Got {len(self.stock_data)} data points for {stock_symbol}")
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
        time = self.curtime
        if time in self.stock_data.index:
            mid_price = (float(self.stock_data.loc[time, "High"]) + float(self.stock_data.loc[time, "Low"]))/2
            return mid_price
        else:
            # Try to find the closest available timestamp
            available_times = self.stock_data.index
            if len(available_times) == 0:
                print(f"DEBUG: No stock data available for {self.ticker}")
                return None
            
            # Debug: Print available times for first few calls
            if not hasattr(self, '_debug_printed'):
                print(f"DEBUG: Available times for {self.ticker}: {available_times[:5].tolist()}...")
                print(f"DEBUG: Requested time: {time}")
                self._debug_printed = True
            
            # Find the closest time (within reasonable range)
            time_diff = abs(available_times - time)
            closest_idx = time_diff.argmin()
            closest_time = available_times[closest_idx]
            
            # Only use closest time if it's within 2 hours (for intraday) or 1 day (for daily)
            # Check if this is intraday data by looking at the time difference between consecutive points
            if len(available_times) > 1:
                time_gap = available_times[1] - available_times[0]
                is_intraday = time_gap <= timedelta(hours=1)
            else:
                is_intraday = True  # Assume intraday if we can't determine
            
            max_diff = timedelta(hours=2) if is_intraday else timedelta(days=1)
            if abs(closest_time - time) <= max_diff:
                mid_price = (float(self.stock_data.loc[closest_time, "High"]) + float(self.stock_data.loc[closest_time, "Low"]))/2
                # Debug: print when we're using closest time
                if abs(closest_time - time) > timedelta(minutes=5):  # Only print if significant difference
                    print(f"Using closest available time {closest_time} for requested time {time} (diff: {abs(closest_time - time)})")
                return mid_price
            else:
                # Market is truly closed (no data within reasonable range)
                print(f"No data available within {max_diff} of requested time {time} for {self.ticker}")
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