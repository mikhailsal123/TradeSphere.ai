import datetime
import logging
from StockData import StockData
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

_plog = logging.getLogger(__name__)

class Portfolio:
    def __init__(self, cash, var1, var2=None, positions=None, past_trades=None, yf_interval='1d'):
        self.cash = cash     # Starting cash
        self.var1 = var1
        self.var2 = var2
        # Must match simulation bar interval; otherwise intraday sims used daily bars in get_value/PnL
        self.yf_interval = yf_interval
        self.allow_daily_fallback = yf_interval == '1d'

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
        # Long shares opened only via beta hedge (margin); unwind separately from user buys
        self.hedge_long_positions = {}
        # One StockData per ticker for this date range — avoids re-downloading Yahoo on every mark
        self._stock_cache = {}

    def _stock_data(self, ticker):
        if ticker not in self._stock_cache:
            self._stock_cache[ticker] = StockData(
                ticker, self.var1, self.var2, self.yf_interval, self.allow_daily_fallback
            )
        return self._stock_cache[ticker]

    def _normalize_timestamp(self, ts):
        """Coerce timeline keys to datetime so sorting and date math stay consistent."""
        if ts is None:
            return datetime.now().replace(microsecond=0)
        if isinstance(ts, datetime):
            return ts.replace(microsecond=0)
        if hasattr(ts, 'to_pydatetime'):
            return ts.to_pydatetime().replace(microsecond=0)
        s = str(ts).strip()
        if ':' in s:
            try:
                return datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S').replace(microsecond=0)
            except ValueError:
                pass
            try:
                return datetime.strptime(s[:16], '%Y-%m-%d %H:%M').replace(microsecond=0)
            except ValueError:
                pass
        return datetime.strptime(s[:10], '%Y-%m-%d')

    def _sorted_timeline_keys(self):
        return sorted(self.change_over_time.keys(), key=self._normalize_timestamp)

    def _periods_per_year(self):
        """
        Effective number of return observations per year for annualizing bar-to-bar metrics.
        Uses ~390 minutes per 6.5h U.S. RTH session × 252 trading days for minute-based bars.
        """
        yf = getattr(self, 'yf_interval', '1d') or '1d'
        if yf == '1d':
            return 252.0
        if isinstance(yf, str) and yf.endswith('m'):
            try:
                bar_m = int(yf[:-1])
                if bar_m <= 0:
                    return 252.0
                bars_per_day = max(1.0, 390.0 / float(bar_m))
                return 252.0 * bars_per_day
            except ValueError:
                return 252.0
        return 252.0

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
        timestamp = self._normalize_timestamp(timestamp)
        position_val = self.cash
        market_closed = False
        
        for position in self.positions.keys():
            sd = self._stock_data(position)
            sd.curtime = timestamp  # Set the current time for the stock data
            market_price = sd.get_price()
            if(market_price is None):
                market_closed = True
                break
            position_val += (market_price * self.positions[position])
        
        # Handle short positions if they exist
        for position, short_shares in self.short_positions.items():
            if short_shares > 0:  # Only process if we have short shares
                sd = self._stock_data(position)
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
                last_timestamp = max(self.change_over_time.keys(), key=self._normalize_timestamp)
                position_val = self.change_over_time[last_timestamp]
                _plog.debug("Market closed at %s; using last value $%.2f", timestamp, position_val)
            else:
                # If no previous data, just return cash value
                position_val = self.cash
                _plog.debug("Market closed at %s; no prior value, cash $%.2f", timestamp, position_val)
        
        # Track value over time
        self.change_over_time[timestamp] = position_val
        return position_val

    def get_PNL(self, timestamp):
        value = self.get_value(timestamp)
        try:
            return float(value) - float(self.original_value)
        except (TypeError, ValueError):
            return 0.0
    
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
        
        elif trade_type == "buy_margin":
            # Long on margin: pay half in cash, half backed by hedge margin pool (mirrors short margin)
            trade_value = price * shares
            margin_required = trade_value * 0.5
            cash_required = trade_value - margin_required
            if self.get_hedge_margin_balance() < margin_required:
                return False, (
                    f"Insufficient hedge margin. Need ${margin_required:.2f}, "
                    f"have ${self.get_hedge_margin_balance():.2f}"
                )
            if self.cash < cash_required:
                return False, f"Insufficient cash for margin buy. Need ${cash_required:.2f}, have ${self.cash:.2f}"
            self.cash -= cash_required
            self.hedge_margin_used += margin_required
            self.positions[ticker] = self.positions.get(ticker, 0) + shares
            self.hedge_long_positions[ticker] = self.hedge_long_positions.get(ticker, 0) + shares
            hedge_trade = {
                'timestamp': timestamp,
                'ticker': ticker,
                'action': 'buy_margin',
                'shares': shares,
                'price': price,
                'value': trade_value,
                'margin_used': margin_required,
                'cash_paid': cash_required,
            }
            self.hedge_trades.append(hedge_trade)
            return True, f"Hedged: Bought {shares} {ticker} @ ${price:.2f} on margin (cash ${cash_required:.2f}, margin ${margin_required:.2f})"

        elif trade_type == "sell_hedge_long":
            # Close hedge-initiated long only (not arbitrary user position)
            trade_value = price * shares
            hl = self.hedge_long_positions.get(ticker, 0)
            if hl < shares:
                return False, f"Insufficient hedge long. Have {hl} hedge long, trying to sell {shares}"
            pos = self.positions.get(ticker, 0)
            if pos < shares:
                return False, f"Insufficient position. Have {pos} shares, trying to sell {shares}"
            self.cash += trade_value
            self.positions[ticker] = pos - shares
            if self.positions[ticker] <= 0:
                del self.positions[ticker]
            self.hedge_long_positions[ticker] = hl - shares
            if self.hedge_long_positions[ticker] <= 0:
                del self.hedge_long_positions[ticker]
            margin_released = trade_value * 0.5
            self.hedge_margin_used = max(0, self.hedge_margin_used - margin_released)
            hedge_trade = {
                'timestamp': timestamp,
                'ticker': ticker,
                'action': 'sell_hedge_long',
                'shares': shares,
                'price': price,
                'value': trade_value,
                'margin_released': margin_released,
            }
            self.hedge_trades.append(hedge_trade)
            return True, f"Hedged: Sold {shares} {ticker} @ ${price:.2f} (closed hedge long, margin released ${margin_released:.2f})"

        return False, "Invalid trade type"

    def summary(self, timestamp):
        print(f"CASH: ${self.cash}")
        print("POSITIONS:")
        for ticker, shares in self.positions.items():
            sd = self._stock_data(ticker)
            sd.curtime = timestamp  # Set the current time for the stock data
            market_price = sd.get_price()
            print(f"  {ticker}: {shares} shares @ ${market_price}")
        print(f"P&L: ${self.get_PNL(timestamp):,.2f}")
        print(f"Current Value: ${self.get_value(timestamp):,.2f}")

    def buy(self, ticker, price, shares, timestamp):
        """
        Buy shares of a stock with cash validation to prevent exceeding initial portfolio value.
        """
        sd = self._stock_data(ticker)
        sd.curtime = timestamp  # Set the current time for the stock data
        market_price = sd.get_price()
        if(market_price is None):
            _plog.debug("Market closed; no price for %s", ticker)
            return

        if(market_price > price):
            _plog.debug("Buy refused: mkt %.2f > limit %.2f", market_price, price)
            return 
        
        # Use the lower of limit price or market price
        execution_price = min(price, market_price)
        
        # Check if we can afford this purchase
        can_afford, reason = self.can_afford_purchase(execution_price, shares, timestamp)
        if not can_afford:
            _plog.debug("Purchase denied: %s", reason)
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
        
        _plog.debug(
            "Bought %s sh %s @ %.2f (cost %.2f); cash %.2f",
            shares, ticker, execution_price, cost, self.cash,
        )
    
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
        """Sell at market when price is 0 (simulation market order); otherwise limit-style floor at `price`."""
        sd = self._stock_data(ticker)
        sd.curtime = timestamp  # Set the current time for the stock data
        market_price = sd.get_price()
        if(market_price is None):
            return

        if price and market_price < price:
            _plog.debug("Sell refused: mkt below limit %s", price)
            return
        price = max(float(price or 0), market_price)

        if self.positions.get(ticker, 0) >= shares:
            self.positions[ticker] -= shares
            self.cash += price * shares
            self.past_trades.append({'action': 'SELL', 'ticker': ticker, 'price': price, 'shares': shares, 'timestamp': timestamp})
        else:
            _plog.debug("Cannot sell %s sh of %s", shares, ticker)

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
        timestamps = self._sorted_timeline_keys()
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
            period_timestamps = [
                ts for ts in timestamps
                if self._normalize_timestamp(start_ts) <= self._normalize_timestamp(ts) <= self._normalize_timestamp(end_ts)
            ]
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
        timestamps = self._sorted_timeline_keys()
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
            plt.xticks(
                range(len(timestamps)),
                [self._normalize_timestamp(ts).strftime('%m/%d %H:%M') for ts in timestamps],
                rotation=45,
            )
        elif num_points <= 100:
            # Medium dataset: show every few labels
            step = max(1, num_points // 10)
            tick_positions = range(0, len(timestamps), step)
            tick_labels = [self._normalize_timestamp(timestamps[i]).strftime('%m/%d') for i in tick_positions]
            plt.xticks(tick_positions, tick_labels, rotation=45)
        else:
            # Large dataset: show fewer labels
            step = max(1, num_points // 8)
            tick_positions = range(0, len(timestamps), step)
            tick_labels = [self._normalize_timestamp(timestamps[i]).strftime('%m/%d') for i in tick_positions]
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

    def calculate_sharpe_ratio(self, risk_free_rate=0.02, period='auto'):
        """
        Calculate the Sharpe ratio for the portfolio.
        
        The Sharpe ratio measures risk-adjusted returns by comparing the excess return
        of the portfolio to its volatility (standard deviation).
        
        Args:
            risk_free_rate (float): Annual risk-free rate (default 2% = 0.02)
            period (str): 'auto' uses yf_interval to set annualization; or 'daily', 'weekly', etc.
        
        Returns:
            float: Sharpe ratio, or None if insufficient data
        """
        if len(self.change_over_time) < 2:
            print("Insufficient data for Sharpe ratio calculation. Need at least 2 data points.")
            return None
        
        # Get sorted values and calculate returns
        timestamps = self._sorted_timeline_keys()
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
        
        if period == 'auto':
            periods_per_year = float(self._periods_per_year())
        elif period == 'daily':
            periods_per_year = 252.0
        elif period == 'weekly':
            periods_per_year = 52.0
        elif period == 'monthly':
            periods_per_year = 12.0
        elif period == 'annual':
            periods_per_year = 1.0
        else:
            print(f"Invalid period '{period}'. Using auto annualization.")
            periods_per_year = float(self._periods_per_year())
        
        rf_per_period = risk_free_rate / periods_per_year
        excess_returns = returns - rf_per_period
        std = np.std(returns, ddof=1)
        if std == 0 or not np.isfinite(std):
            print("Portfolio has zero volatility. Sharpe ratio is undefined.")
            return None
        
        # Annualized Sharpe (bar returns ~ i.i.d. approximation)
        sharpe_ratio = (np.mean(excess_returns) * periods_per_year) / (std * np.sqrt(periods_per_year))
        return float(sharpe_ratio) if np.isfinite(sharpe_ratio) else None
    
    def calculate_volatility(self, period='auto'):
        """
        Calculate annualized volatility of portfolio simple returns between marks.
        
        Args:
            period (str): 'auto' uses yf_interval for sqrt-scaling; or 'daily', etc.
        
        Returns:
            float: Annualized volatility as a decimal (e.g. 0.15 for 15%), or None
        """
        if len(self.change_over_time) < 2:
            print("Insufficient data for volatility calculation. Need at least 2 data points.")
            return None
        
        # Get sorted values and calculate returns
        timestamps = self._sorted_timeline_keys()
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
        
        if period == 'auto':
            periods_per_year = float(self._periods_per_year())
        elif period == 'daily':
            periods_per_year = 252.0
        elif period == 'weekly':
            periods_per_year = 52.0
        elif period == 'monthly':
            periods_per_year = 12.0
        elif period == 'annual':
            periods_per_year = 1.0
        else:
            periods_per_year = float(self._periods_per_year())
        
        std = np.std(returns, ddof=1)
        if not np.isfinite(std):
            return None
        volatility = std * np.sqrt(periods_per_year)
        return float(volatility) if np.isfinite(volatility) else None
    
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
        timestamps = self._sorted_timeline_keys()
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
        
        # Calculate metrics (annualization matches bar interval, not hard-coded 252 days of bars)
        if values[0] == 0:
            return None
        total_return = (values[-1] - values[0]) / values[0] * 100
        ppy = float(self._periods_per_year())
        n = len(returns)
        growth = values[-1] / values[0]
        annualized_return = (growth ** (ppy / n) - 1) if growth > 0 and n > 0 else None
        vol_dec = np.std(returns, ddof=1) * np.sqrt(ppy)
        volatility = vol_dec * 100
        sharpe_ratio = self.calculate_sharpe_ratio(risk_free_rate, period='auto')
        
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
            'annualized_return_pct': round(annualized_return * 100, 2) if annualized_return is not None else None,
            'volatility_pct': round(volatility, 2),
            'sharpe_ratio': round(sharpe_ratio, 3) if sharpe_ratio is not None else None,
            'max_drawdown_pct': round(max_drawdown, 2),
            'data_points': len(values),
            'time_period_days': (
                self._normalize_timestamp(timestamps[-1]) - self._normalize_timestamp(timestamps[0])
            ).days
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
            from datetime import time as dt_time

            timestamps = self._sorted_timeline_keys()
            portfolio_values = [self.change_over_time[ts] for ts in timestamps]
            norm_ts = [self._normalize_timestamp(t) for t in timestamps]

            benchmark_start = (norm_ts[0] - timedelta(days=7)).strftime('%Y-%m-%d')
            benchmark_end = (norm_ts[-1] + timedelta(days=7)).strftime('%Y-%m-%d')

            # Last mark-to-market per calendar day → daily returns vs daily benchmark (avoids ~0 market returns when intraday portfolio steps use the same daily ^GSPC bar).
            last_by_day = {}
            for t, v in zip(norm_ts, portfolio_values):
                last_by_day[t.date()] = v
            sorted_days = sorted(last_by_day.keys())

            aligned_p = []
            aligned_b = []
            ann_ppy = 252.0

            if len(sorted_days) >= 2:
                bd_daily = StockData(
                    benchmark_ticker, benchmark_start, benchmark_end, '1d', allow_daily_fallback=True
                )
                if not bd_daily.stock_data.empty:
                    for i in range(1, len(sorted_days)):
                        d0, d1 = sorted_days[i - 1], sorted_days[i]
                        v0, v1 = last_by_day[d0], last_by_day[d1]
                        if v0 == 0:
                            continue
                        bd_daily.curtime = datetime.combine(d0, dt_time(16, 0))
                        p0 = bd_daily.get_price()
                        bd_daily.curtime = datetime.combine(d1, dt_time(16, 0))
                        p1 = bd_daily.get_price()
                        if p0 is not None and p1 is not None and p0 > 0 and p1 > 0:
                            aligned_p.append((v1 - v0) / v0)
                            aligned_b.append((p1 - p0) / p0)

            if len(aligned_p) < 3:
                aligned_p = []
                aligned_b = []
                yf = getattr(self, 'yf_interval', '1d') or '1d'
                v2 = self.var2
                if v2 is not None and len(str(v2)) == 10:
                    bd_bar = StockData(
                        benchmark_ticker, str(self.var1), str(v2), yf, allow_daily_fallback=True
                    )
                else:
                    bd_bar = StockData(
                        benchmark_ticker, benchmark_start, benchmark_end, '1d', allow_daily_fallback=True
                    )
                if bd_bar.stock_data.empty:
                    print(f"Could not retrieve benchmark data for {benchmark_ticker}")
                    return None
                for i in range(1, len(timestamps)):
                    if portfolio_values[i - 1] == 0:
                        continue
                    pr = (portfolio_values[i] - portfolio_values[i - 1]) / portfolio_values[i - 1]
                    bd_bar.curtime = norm_ts[i - 1]
                    p0 = bd_bar.get_price()
                    bd_bar.curtime = norm_ts[i]
                    p1 = bd_bar.get_price()
                    if p0 is not None and p1 is not None and p0 > 0 and p1 > 0:
                        aligned_p.append(pr)
                        aligned_b.append((p1 - p0) / p0)
                ann_ppy = float(self._periods_per_year())

            if len(aligned_p) < 3:
                print(f"Insufficient aligned data points for beta: {len(aligned_p)} (need at least 3)")
                return None

            pr = np.asarray(aligned_p, dtype=float)
            br = np.asarray(aligned_b, dtype=float)
            cov = np.cov(pr, br, ddof=1)[0, 1]
            var_m = np.var(br, ddof=1)
            if var_m == 0 or not np.isfinite(var_m):
                print("Benchmark variance is zero - cannot calculate beta")
                return None
            beta = cov / var_m

            std_p = np.std(pr, ddof=1)
            std_b = np.std(br, ddof=1)
            if len(pr) > 1 and std_p > 0 and std_b > 0:
                correlation = np.corrcoef(pr, br)[0, 1]
                if np.isnan(correlation):
                    correlation = 0.0
            else:
                correlation = 0.0

            r_squared = correlation ** 2

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
                'beta': round(float(beta), 3),
                'correlation': round(float(correlation), 3),
                'r_squared': round(float(r_squared), 3),
                'benchmark_ticker': benchmark_ticker,
                'data_points': len(aligned_p),
                'interpretation': beta_interpretation,
                'portfolio_volatility': round(float(std_p * np.sqrt(ann_ppy)), 4),
                'benchmark_volatility': round(float(std_b * np.sqrt(ann_ppy)), 4),
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