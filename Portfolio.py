import datetime
from StockData import StockData
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

class Portfolio:
    def __init__(self, cash, var1, var2 = None, positions = None, past_trades = None): 
        self.cash = cash     # Starting cash
        self.var1 = var1 
        self.var2 = var2

        if positions is not None:
            self.positions = positions
        else:
            self.positions = {}       # {ticker: shares held}
        
        if past_trades is not None:
            self.past_trades = past_trades
        else:
            self.past_trades = []
        
        self.original_value = cash  #keep track of original value fo the portfolio
        self.change_over_time = {}  # {timestamp: portfolio_value}
        
        # Hedge margin tracking (separate from regular cash)
        self.hedge_margin_used = 0.0  # Amount of margin used for hedging
        self.hedge_margin_available = cash * 0.5  # 50% of portfolio can be used for hedge margin
        self.hedge_trades = []  # Track all hedge transactions
        self.short_positions = {}  # Track short positions for hedging
    
    def get_total_portfolio_value(self, timestamp):
        """Get the total portfolio value (cash + positions) at a given timestamp"""
        return self.get_value(timestamp)
    
    def can_afford_purchase(self, price, shares, timestamp):
        """
        Check if the portfolio can afford a purchase.
        Simple logic: only check if we have enough cash available.
        The portfolio value constraint is enforced by the simulation logic.
        Returns (can_afford, reason)
        """
        cost = price * shares
        
        # Check if we have enough cash
        if self.cash < cost:
            return False, f"Insufficient cash. Need ${cost:,.2f}, have ${self.cash:,.2f}"
        
        return True, "Purchase allowed"
    
    def get_value(self, timestamp):
        position_val = self.cash
        market_closed = False
        
        for position in self.positions.keys():
            sd = StockData(position, self.var1, self.var2)
            sd.curtime = timestamp  # Set the current time for the stock data
            market_price = sd.get_price()
            if(market_price is None):
                market_closed = True
                break
            position_val += (market_price * self.positions[position])
        
        # Handle short positions if they exist
        for position, short_shares in self.short_positions.items():
            if short_shares > 0:  # Only process if we have short shares
                sd = StockData(position, self.var1, self.var2)
                sd.curtime = timestamp
                market_price = sd.get_price()
                if(market_price is None):
                    market_closed = True
                    break
                # Short positions: we owe shares at current market price
                # If price goes up, we lose money (owe more)
                # If price goes down, we make money (owe less)
                # The cash from shorting is already in self.cash, so we subtract current value
                position_val -= (market_price * short_shares)
        
        # If market is closed, use the last known portfolio value
        if market_closed:
            if self.change_over_time:
                # Get the most recent portfolio value
                last_timestamp = max(self.change_over_time.keys())
                position_val = self.change_over_time[last_timestamp]
                print(f"Market closed at {timestamp}. Using last known value: ${position_val:,.2f}")
            else:
                # If no previous data, just return cash value
                position_val = self.cash
                print(f"Market closed at {timestamp}. No previous data. Using cash value: ${position_val:,.2f}")
        
        # Track value over time
        self.change_over_time[timestamp] = position_val
        return position_val

    def get_PNL(self, timestamp):
        value = self.get_value(timestamp)
        if value is not None:
            return value - self.original_value
    
    def get_hedge_margin_balance(self):
        """Get available hedge margin balance"""
        return self.hedge_margin_available - self.hedge_margin_used
    
    def execute_hedge_trade(self, ticker, price, shares, timestamp, trade_type="short"):
        """Execute a hedge trade and update margin usage"""
        if trade_type == "short":
            # Short sale: receive cash, owe shares
            trade_value = price * shares
            margin_required = trade_value * 0.5  # 50% margin requirement
            
            if self.get_hedge_margin_balance() >= margin_required:
                # Execute short trade
                # Don't modify positions - short positions are tracked separately
                self.cash += trade_value
                self.hedge_margin_used += margin_required
                
                # Track short position
                self.short_positions[ticker] = self.short_positions.get(ticker, 0) + shares
                
                # Record hedge trade
                hedge_trade = {
                    'timestamp': timestamp,
                    'ticker': ticker,
                    'action': 'short',
                    'shares': shares,
                    'price': price,
                    'value': trade_value,
                    'margin_used': margin_required
                }
                self.hedge_trades.append(hedge_trade)
                
                return True, f"Hedged: Shorted {shares} {ticker} @ ${price:.2f} (margin: ${margin_required:.2f})"
            else:
                return False, f"Insufficient hedge margin. Need ${margin_required:.2f}, have ${self.get_hedge_margin_balance():.2f}"
        
        elif trade_type == "buy":
            # Buy back: pay cash, reduce short position
            trade_value = price * shares
            
            # Check if we have enough short position to buy back
            current_shorts = self.short_positions.get(ticker, 0)
            if current_shorts < shares:
                return False, f"Insufficient short position. Have {current_shorts} shorts, trying to buy back {shares}"
            
            # Check if we have enough cash
            if self.cash < trade_value:
                return False, f"Insufficient cash. Need ${trade_value:.2f}, have ${self.cash:.2f}"
            
            # Execute buy back trade
            # Don't add to positions - just close out the short
            self.cash -= trade_value
            
            # Reduce short position
            self.short_positions[ticker] = current_shorts - shares
            if self.short_positions[ticker] <= 0:
                del self.short_positions[ticker]
            
            # Release margin (50% of the short value)
            margin_released = trade_value * 0.5
            self.hedge_margin_used = max(0, self.hedge_margin_used - margin_released)
            
            # Record hedge trade
            hedge_trade = {
                'timestamp': timestamp,
                'ticker': ticker,
                'action': 'buy',
                'shares': shares,
                'price': price,
                'value': trade_value,
                'margin_released': margin_released
            }
            self.hedge_trades.append(hedge_trade)
            
            return True, f"Hedged: Bought back {shares} {ticker} @ ${price:.2f} (margin released: ${margin_released:.2f})"
        
        return False, "Invalid trade type"

    def summary(self, timestamp):
        print(f"CASH: ${self.cash}")
        print("POSITIONS:")
        for ticker, shares in self.positions.items():
            sd = StockData(ticker, self.var1, self.var2)
            sd.curtime = timestamp  # Set the current time for the stock data
            market_price = sd.get_price()
            print(f"  {ticker}: {shares} shares @ ${market_price}")
        print(f"P&L: ${self.get_PNL(timestamp):,.2f}")
        print(f"Current Value: ${self.get_value(timestamp):,.2f}")

    def buy(self, ticker, price, shares, timestamp):
        """
        Buy shares of a stock with cash validation to prevent exceeding initial portfolio value.
        """
        sd = StockData(ticker, self.var1, self.var2)
        sd.curtime = timestamp  # Set the current time for the stock data
        market_price = sd.get_price()
        if(market_price is None):
            print(f"Market closed - cannot get price for {ticker}")
            return

        if(market_price > price):
            print(f"Order refused. Market Price ${market_price:.2f} higher than limit price ${price:.2f}")
            return 
        
        # Use the lower of limit price or market price
        execution_price = min(price, market_price)
        
        # Check if we can afford this purchase
        can_afford, reason = self.can_afford_purchase(execution_price, shares, timestamp)
        if not can_afford:
            print(f"Purchase denied: {reason}")
            return
        
        # Execute the purchase
        cost = execution_price * shares
        self.cash -= cost
        self.positions[ticker] = self.positions.get(ticker, 0) + shares
        
        # Record the trade
        trade_record = {
            'action': 'BUY', 
            'ticker': ticker, 
            'price': execution_price, 
            'shares': shares, 
            'total_value': cost,
            'timestamp': timestamp,
            'cash_after': self.cash
        }
        self.past_trades.append(trade_record)
        
        print(f"✅ Bought {shares} shares of {ticker} at ${execution_price:.2f} (Total: ${cost:,.2f})")
        print(f"   Cash remaining: ${self.cash:,.2f}")
        print(f"   Portfolio value: ${self.get_total_portfolio_value(timestamp):,.2f}")
    
    def get_portfolio_stats(self, timestamp):
        """
        Get comprehensive portfolio statistics including cash validation info.
        """
        current_value = self.get_total_portfolio_value(timestamp)
        cash_ratio = (self.cash / current_value * 100) if current_value > 0 else 0
        positions_value = current_value - self.cash
        
        stats = {
            'initial_cash': self.original_value,
            'current_cash': self.cash,
            'positions_value': positions_value,
            'total_value': current_value,
            'cash_ratio': cash_ratio,
            'can_trade': self.cash > 0,
            'max_purchase_power': self.cash,
            'total_trades': len(self.past_trades)
        }
        
        return stats
    
    def is_portfolio_valid(self, timestamp):
        """
        Check if the portfolio is in a valid state (not exceeding initial cash).
        Returns (is_valid, message)
        """
        current_value = self.get_total_portfolio_value(timestamp)
        
        if current_value > self.original_value:
            return False, f"Portfolio value (${current_value:,.2f}) exceeds initial cash (${self.original_value:,.2f})"
        
        return True, "Portfolio is within valid limits"
    
    def sell(self, ticker, price, shares, timestamp):
        sd = StockData(ticker, self.var1, self.var2)
        sd.curtime = timestamp  # Set the current time for the stock data
        market_price = sd.get_price()
        if(market_price is None):
            return

        if(market_price < price):
            print(f"Order refused. Market Price lower than {price}")
            return 
        price = max(price, market_price)

        if self.positions.get(ticker, 0) >= shares:
            self.positions[ticker] -= shares
            self.cash += price * shares
            self.past_trades.append({'action': 'SELL', 'ticker': ticker, 'price': price, 'shares': shares, 'timestamp': timestamp})
        else:
            print(f"Not enough shares to sell {shares} of {ticker}")

    def plot_portfolio_value(self, title="Portfolio Value Over Time", save_path=None, show_percentage=False, show_plot=True):
        """
        Plot the portfolio value changes over time.
        Shows constant values during market closures.
        
        Args:
            title (str): Title for the plot
            save_path (str): Optional path to save the plot as an image
            show_percentage (bool): If True, show percentage changes from original value
        """
        if not self.change_over_time:
            print("No portfolio value data available. Call get_value() with timestamps first.")
            return
        
        # Sort timestamps and values
        timestamps = sorted(self.change_over_time.keys())
        values = [self.change_over_time[ts] for ts in timestamps]
        
        # Calculate percentage changes if requested
        if show_percentage:
            values = [((val - self.original_value) / self.original_value) * 100 for val in values]
            ylabel = 'Portfolio Value Change (%)'
            title += " (Percentage Change)"
        else:
            ylabel = 'Portfolio Value ($)'
        
        # Determine plot styling based on data size
        num_points = len(timestamps)
        
        # Create the plot with appropriate size
        plt.figure(figsize=(14, 8))
        
        # Adaptive plotting based on data size
        if num_points <= 30:
            # Small dataset: show markers and full detail
            plt.plot(timestamps, values, marker='o', linewidth=2, markersize=4, color='blue', label='Portfolio Value')
        elif num_points <= 100:
            # Medium dataset: show markers but smaller
            plt.plot(timestamps, values, marker='o', linewidth=1.5, markersize=2, color='blue', label='Portfolio Value')
        else:
            # Large dataset: no markers, just line
            plt.plot(timestamps, values, linewidth=2, color='blue', label='Portfolio Value')
        
        # Identify and highlight constant value periods (market closures)
        constant_periods = []
        current_period_start = None
        current_value = None
        
        for i, (ts, val) in enumerate(zip(timestamps, values)):
            if i == 0:
                current_value = val
                current_period_start = ts
            elif val == current_value and i < len(values) - 1:
                # Still in a constant period
                continue
            else:
                # Value changed or end of data
                if current_period_start and i > 1:  # Only highlight if period has multiple points
                    constant_periods.append((current_period_start, timestamps[i-1], current_value))
                current_value = val
                current_period_start = ts
        
        # Highlight constant value periods with different styling
        for start_ts, end_ts, const_val in constant_periods:
            period_timestamps = [ts for ts in timestamps if start_ts <= ts <= end_ts]
            period_values = [self.change_over_time[ts] for ts in period_timestamps]
            plt.plot(period_timestamps, period_values, '--', color='gray', alpha=0.7, linewidth=1)
        
        # Add horizontal line for original value
        if show_percentage:
            plt.axhline(y=0, color='r', linestyle='--', alpha=0.7, label='Original Value (0%)')
        else:
            plt.axhline(y=self.original_value, color='r', linestyle='--', alpha=0.7, label=f'Original Value: ${self.original_value:,.2f}')
        
        # Formatting
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel('Date', fontsize=12)
        plt.ylabel(ylabel, fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Adaptive x-axis formatting based on data size
        if num_points <= 30:
            # Small dataset: show all dates
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=1))
            plt.xticks(rotation=45)
        elif num_points <= 100:
            # Medium dataset: show every few dates
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
            plt.gca().xaxis.set_major_locator(mdates.DayLocator(interval=3))
            plt.xticks(rotation=45)
        else:
            # Large dataset: show weekly/monthly intervals
            if num_points <= 365:
                # Daily data: show weekly intervals
                plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
                plt.gca().xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
            else:
                # More than a year: show monthly intervals
                plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                plt.gca().xaxis.set_major_locator(mdates.MonthLocator(interval=1))
            plt.xticks(rotation=45)
        
        # Format y-axis based on display type
        if show_percentage:
            plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:.1f}%'))
        else:
            plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        # Adjust y-axis to show changes more proportionally
        if len(values) > 1:
            min_val = min(values)
            max_val = max(values)
            range_val = max_val - min_val
            
            # Add padding but limit it to reasonable bounds
            if range_val > 0:
                if show_percentage:
                    # More sensitive scaling for percentage view - smaller padding
                    padding = max(range_val * 0.2, 0.1)  # 20% padding, minimum 0.1%
                else:
                    padding = max(range_val * 0.1, 100)  # At least $100 padding
                plt.ylim(min_val - padding, max_val + padding)
            else:
                # If all values are the same, add small padding around the value
                if show_percentage:
                    plt.ylim(min_val - 0.1, min_val + 0.1)  # Small percentage padding
                else:
                    plt.ylim(min_val - 100, min_val + 100)  # Small dollar padding
        
        plt.tight_layout()
        
        # Save if path provided
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {save_path}")
        
        if show_plot:
            plt.show()

    def plot_pnl(self, title="Portfolio P&L Over Time", save_path=None, show_plot=True):
        """
        Plot the portfolio profit and loss over time.
        
        Args:
            title (str): Title for the plot
            save_path (str): Optional path to save the plot as an image
        """
        if not self.change_over_time:
            print("No portfolio value data available. Call get_value() with timestamps first.")
            return
        
        # Sort timestamps and calculate P&L
        timestamps = sorted(self.change_over_time.keys())
        pnl_values = [self.change_over_time[ts] - self.original_value for ts in timestamps]
        
        # Determine plot styling based on data size
        num_points = len(timestamps)
        
        # Create the plot with appropriate size
        plt.figure(figsize=(14, 8))
        
        # Adaptive plotting based on data size
        if num_points <= 50:
            # Small dataset: use bars with different colors for profit/loss
            colors = ['green' if pnl >= 0 else 'red' for pnl in pnl_values]
            plt.bar(range(len(timestamps)), pnl_values, color=colors, alpha=0.7, width=0.8)
        else:
            # Large dataset: use line plot to avoid overcrowding
            colors = ['green' if pnl >= 0 else 'red' for pnl in pnl_values]
            plt.plot(range(len(timestamps)), pnl_values, linewidth=2, color='blue', alpha=0.8)
            # Add colored area under the line
            plt.fill_between(range(len(timestamps)), pnl_values, 0, 
                           color=[('green' if pnl >= 0 else 'red') for pnl in pnl_values], 
                           alpha=0.3)
        
        # Add horizontal line at zero
        plt.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        
        # Formatting
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel('Time Points', fontsize=12)
        plt.ylabel('Profit/Loss ($)', fontsize=12)
        plt.grid(True, alpha=0.3)
        
        # Adaptive x-axis labels based on data size
        if num_points <= 20:
            # Small dataset: show all labels
            plt.xticks(range(len(timestamps)), [ts.strftime('%m/%d %H:%M') for ts in timestamps], rotation=45)
        elif num_points <= 100:
            # Medium dataset: show every few labels
            step = max(1, num_points // 10)
            tick_positions = range(0, len(timestamps), step)
            tick_labels = [timestamps[i].strftime('%m/%d') for i in tick_positions]
            plt.xticks(tick_positions, tick_labels, rotation=45)
        else:
            # Large dataset: show fewer labels
            step = max(1, num_points // 8)
            tick_positions = range(0, len(timestamps), step)
            tick_labels = [timestamps[i].strftime('%m/%d') for i in tick_positions]
            plt.xticks(tick_positions, tick_labels, rotation=45)
        
        # Format y-axis as currency
        plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
        
        plt.tight_layout()
        
        # Save if path provided
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {save_path}")
        
        if show_plot:
            plt.show()

    def calculate_sharpe_ratio(self, risk_free_rate=0.02, period='daily'):
        """
        Calculate the Sharpe ratio for the portfolio.
        
        The Sharpe ratio measures risk-adjusted returns by comparing the excess return
        of the portfolio to its volatility (standard deviation).
        
        Args:
            risk_free_rate (float): Annual risk-free rate (default 2% = 0.02)
            period (str): Period of returns ('daily', 'weekly', 'monthly', 'annual')
        
        Returns:
            float: Sharpe ratio, or None if insufficient data
        """
        if len(self.change_over_time) < 2:
            print("Insufficient data for Sharpe ratio calculation. Need at least 2 data points.")
            return None
        
        # Get sorted values and calculate returns
        timestamps = sorted(self.change_over_time.keys())
        values = [self.change_over_time[ts] for ts in timestamps]
        
        # Calculate percentage returns
        returns = []
        for i in range(1, len(values)):
            if values[i-1] != 0:  # Avoid division by zero
                daily_return = (values[i] - values[i-1]) / values[i-1]
                returns.append(daily_return)
        
        if len(returns) < 2:
            print("Insufficient return data for Sharpe ratio calculation.")
            return None
        
        # Convert to numpy array for easier calculations
        returns = np.array(returns)
        
        # Calculate annualized metrics based on period
        if period == 'daily':
            periods_per_year = 252  # Trading days per year
        elif period == 'weekly':
            periods_per_year = 52
        elif period == 'monthly':
            periods_per_year = 12
        elif period == 'annual':
            periods_per_year = 1
        else:
            print(f"Invalid period '{period}'. Using 'daily'.")
            periods_per_year = 252
        
        # Annualize the risk-free rate
        daily_risk_free_rate = risk_free_rate / periods_per_year
        
        # Calculate excess returns
        excess_returns = returns - daily_risk_free_rate
        
        # Calculate Sharpe ratio
        if np.std(returns) == 0:
            print("Portfolio has zero volatility. Sharpe ratio is undefined.")
            return None
        
        # Annualized Sharpe ratio
        sharpe_ratio = (np.mean(excess_returns) * periods_per_year) / (np.std(returns) * np.sqrt(periods_per_year))
        
        return sharpe_ratio
    
    def calculate_volatility(self, period='daily'):
        """
        Calculate the volatility (standard deviation) of portfolio returns.
        
        Args:
            period (str): Period of returns ('daily', 'weekly', 'monthly', 'annual')
        
        Returns:
            float: Volatility, or None if insufficient data
        """
        if len(self.change_over_time) < 2:
            print("Insufficient data for volatility calculation. Need at least 2 data points.")
            return None
        
        # Get sorted values and calculate returns
        timestamps = sorted(self.change_over_time.keys())
        values = [self.change_over_time[ts] for ts in timestamps]
        
        # Calculate percentage returns
        returns = []
        for i in range(1, len(values)):
            if values[i-1] != 0:  # Avoid division by zero
                daily_return = (values[i] - values[i-1]) / values[i-1]
                returns.append(daily_return)
        
        if len(returns) < 2:
            print("Insufficient return data for volatility calculation.")
            return None
        
        # Convert to numpy array
        returns = np.array(returns)
        
        # Calculate annualized volatility based on period
        if period == 'daily':
            periods_per_year = 252  # Trading days per year
        elif period == 'weekly':
            periods_per_year = 52
        elif period == 'monthly':
            periods_per_year = 12
        elif period == 'annual':
            periods_per_year = 1
        else:
            print(f"Invalid period '{period}'. Using 'daily'.")
            periods_per_year = 252
        
        # Annualized volatility
        volatility = np.std(returns) * np.sqrt(periods_per_year)
        
        return volatility
    
    def calculate_returns_summary(self, risk_free_rate=0.02):
        """Calculate a comprehensive summary of portfolio returns and risk metrics.
        
        Args:
            risk_free_rate (float): Annual risk-free rate (default 2% = 0.02)
        
        Returns:
            dict: Dictionary containing various return and risk metrics"""
            
        if len(self.change_over_time) < 2:
            print("Insufficient data for returns summary. Need at least 2 data points.")
            return None
        
        # Get sorted values and calculate returns
        timestamps = sorted(self.change_over_time.keys())
        values = [self.change_over_time[ts] for ts in timestamps]
        
        # Calculate percentage returns
        returns = []
        for i in range(1, len(values)):
            if values[i-1] != 0:  # Avoid division by zero
                daily_return = (values[i] - values[i-1]) / values[i-1]
                returns.append(daily_return)
        
        if len(returns) < 2:
            print("Insufficient return data for summary calculation.")
            return None
        
        returns = np.array(returns)
        
        # Calculate metrics
        total_return = (values[-1] - values[0]) / values[0] * 100
        annualized_return = (1 + total_return/100) ** (252/len(returns)) - 1
        volatility = np.std(returns) * np.sqrt(252) * 100
        sharpe_ratio = self.calculate_sharpe_ratio(risk_free_rate)
        
        # Calculate maximum drawdown
        peak = values[0]
        max_drawdown = 0
        for value in values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        summary = {
            'total_return_pct': round(total_return, 2),
            'annualized_return_pct': round(annualized_return * 100, 2),
            'volatility_pct': round(volatility, 2),
            'sharpe_ratio': round(sharpe_ratio, 3) if sharpe_ratio else None,
            'max_drawdown_pct': round(max_drawdown, 2),
            'data_points': len(values),
            'time_period_days': (timestamps[-1] - timestamps[0]).days
        }
        
        return summary

    def calculate_portfolio_beta(self, benchmark_ticker='^GSPC', risk_free_rate=0.02):
        """Calculate the portfolio's beta relative to a benchmark (default: S&P 500).
        
        Beta measures the portfolio's sensitivity to market movements:
        - Beta = 1.0: Moves with the market
        - Beta > 1.0: More volatile than the market (higher risk/reward)
        - Beta < 1.0: Less volatile than the market (lower risk/reward)
        - Beta = 0: No correlation with the market (cash-like)
        
        Args:
            benchmark_ticker (str): Benchmark ticker symbol (default: ^GSPC for S&P 500)
            risk_free_rate (float): Annual risk-free rate (default 2% = 0.02)
        
        Returns:
            dict: Dictionary containing beta calculation results and details
        """
        
        if len(self.change_over_time) < 3:
            print("Insufficient data for beta calculation. Need at least 3 data points.")
            return None
        
        try:
            # Get portfolio data
            timestamps = sorted(self.change_over_time.keys())
            portfolio_values = [self.change_over_time[ts] for ts in timestamps]
            
            # Get benchmark data with extended period to ensure we have enough data
            benchmark_start = (timestamps[0] - timedelta(days=5)).strftime('%Y-%m-%d')
            benchmark_end = (timestamps[-1] + timedelta(days=5)).strftime('%Y-%m-%d')
            
            benchmark_data = StockData(benchmark_ticker, benchmark_start, benchmark_end)
            
            if benchmark_data.stock_data.empty:
                print(f"Could not retrieve benchmark data for {benchmark_ticker}")
                return None
            
            # Align portfolio and benchmark data by matching available trading days
            aligned_portfolio_returns = []
            aligned_benchmark_returns = []
            
            for i in range(1, len(timestamps)):
                # Get portfolio return for this period
                portfolio_return = (portfolio_values[i] - portfolio_values[i-1]) / portfolio_values[i-1]
                
                # Try to get benchmark prices for both dates
                benchmark_data.curtime = timestamps[i-1]
                price_start = benchmark_data.get_price()
                
                benchmark_data.curtime = timestamps[i]
                price_end = benchmark_data.get_price()
                
                # Only include if we have valid benchmark data for both dates
                if price_start is not None and price_end is not None and price_start > 0:
                    benchmark_return = (price_end - price_start) / price_start
                    aligned_portfolio_returns.append(portfolio_return)
                    aligned_benchmark_returns.append(benchmark_return)
            
            # Need at least 3 data points for meaningful beta calculation
            if len(aligned_portfolio_returns) < 3:
                print(f"Insufficient aligned data points: {len(aligned_portfolio_returns)} (need at least 3)")
                return None
            
            # Convert to numpy arrays
            portfolio_returns = np.array(aligned_portfolio_returns)
            benchmark_returns = np.array(aligned_benchmark_returns)
            
            # Calculate covariance and variance
            covariance = np.cov(portfolio_returns, benchmark_returns)[0, 1]
            benchmark_variance = np.var(benchmark_returns)
            
            # Beta = Covariance(Portfolio, Benchmark) / Variance(Benchmark)
            if benchmark_variance == 0:
                print("Benchmark variance is zero - cannot calculate beta")
                return None
            
            beta = covariance / benchmark_variance
            
            # Calculate correlation coefficient
            if len(portfolio_returns) > 1 and np.std(portfolio_returns) > 0 and np.std(benchmark_returns) > 0:
                correlation = np.corrcoef(portfolio_returns, benchmark_returns)[0, 1]
                if np.isnan(correlation):
                    correlation = 0.0
            else:
                correlation = 0.0
            
            # Calculate R-squared (coefficient of determination)
            r_squared = correlation ** 2
            
            # Interpret beta with more nuanced ranges
            if beta > 1.5:
                beta_interpretation = "Very high beta - Portfolio is significantly more volatile than the market"
            elif beta > 1.2:
                beta_interpretation = "High beta - Portfolio is more volatile than the market"
            elif beta > 0.8:
                beta_interpretation = "Moderate beta - Portfolio moves roughly with the market"
            elif beta > 0.3:
                beta_interpretation = "Low beta - Portfolio is less volatile than the market"
            elif beta > -0.3:
                beta_interpretation = "Very low beta - Portfolio shows little correlation with the market"
            else:
                beta_interpretation = "Negative beta - Portfolio moves opposite to the market"
            
            result = {
                'beta': round(beta, 3),
                'correlation': round(correlation, 3),
                'r_squared': round(r_squared, 3),
                'benchmark_ticker': benchmark_ticker,
                'data_points': len(aligned_portfolio_returns),
                'interpretation': beta_interpretation,
                'portfolio_volatility': round(np.std(portfolio_returns) * np.sqrt(252), 3),  # Annualized
                'benchmark_volatility': round(np.std(benchmark_returns) * np.sqrt(252), 3)  # Annualized
            }
            
            return result
            
        except Exception as e:
            print(f"Error calculating portfolio beta: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

def main():
    A = Portfolio(100000, "60d", "2m")
    
    # Make some trades
    A.buy("AAPL", 225, 100, datetime(2025, 8, 8, 9, 30))
    A.sell("AAPL", 200, 50, datetime(2025, 8, 8, 9, 30))
    A.buy("NVDA", 300, 100, datetime(2025, 8, 8, 9, 30))
    
    # Track portfolio value at different times
    print("Tracking portfolio value over time...")
    A.get_value(datetime(2025, 8, 8, 9, 30))   # After trades
    A.get_value(datetime(2025, 8, 9, 9, 30))   # Next day
    A.get_value(datetime(2025, 8, 10, 9, 30))  # Day after
    A.get_value(datetime(2025, 8, 11, 9, 30))  # Another day
    A.get_value(datetime(2025, 8, 12, 9, 30))  # Final day
    A.get_value(datetime(2025, 8, 13, 9, 30))
    A.get_value(datetime(2025, 8, 14, 9, 30))
    A.get_value(datetime(2025, 8, 15, 9, 30))
    A.get_value(datetime(2025, 8, 16, 9, 30))
    A.get_value(datetime(2025, 8, 17, 9, 30))
    A.get_value(datetime(2025, 8, 18, 9, 30))
    A.get_value(datetime(2025, 8, 19, 9, 30))
    A.get_value(datetime(2025, 9, 1, 9, 30))
    A.get_value(datetime(2025, 9, 2, 9, 30))
    A.get_value(datetime(2025, 9, 3, 9, 30))
    A.get_value(datetime(2025, 9, 8, 9, 30))
    
    A.summary(datetime(2025, 9, 8, 9, 30))
    
    # Calculate risk metrics
    print("\n=== Risk Metrics ===")
    sharpe_ratio = A.calculate_sharpe_ratio()
    volatility = A.calculate_volatility()
    
    if sharpe_ratio is not None:
        print(f"Sharpe Ratio: {sharpe_ratio:.3f}")
    if volatility is not None:
        print(f"Annualized Volatility: {volatility*100:.2f}%")
    
    # Get comprehensive returns summary
    summary = A.calculate_returns_summary()
    if summary:
        print(f"\n=== Returns Summary ===")
        print(f"Total Return: {summary['total_return_pct']}%")
        print(f"Annualized Return: {summary['annualized_return_pct']}%")
        print(f"Volatility: {summary['volatility_pct']}%")
        print(f"Sharpe Ratio: {summary['sharpe_ratio']}")
        print(f"Max Drawdown: {summary['max_drawdown_pct']}%")
        print(f"Data Points: {summary['data_points']}")
        print(f"Time Period: {summary['time_period_days']} days")
    
    # Plot the portfolio value over time
    print("\nGenerating plots...")
    A.plot_portfolio_value("My Portfolio Performance")
    A.plot_portfolio_value("My Portfolio Performance (Percentage View)", show_percentage=True)
    A.plot_pnl("Portfolio Profit & Loss")

if __name__ == "__main__":
    main()