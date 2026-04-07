from Portfolio import Portfolio
from StockData import StockData
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import time

# Initialize starting time and portfolio (use a weekday)
currtime = datetime(2025, 7, 21)  # Monday
start_date_str = currtime.strftime('%Y-%m-%d')
end_date_str = (currtime + relativedelta(months=2)).strftime('%Y-%m-%d')
port = Portfolio(100000, start_date_str, end_date_str)

# Initial purchases
print("Making initial purchases...")
time.sleep(1)
port.buy("NVDA", 400, 100, currtime)  # Buy 100 shares at market price (500 is max price)
port.buy("AMZN", 300, 120, currtime)  # Buy 120 shares at market price (320 is max price)
port.buy("GOOG", 200, 100, currtime)  # Buy 100 shares at market price (600 is max price)

# Initialize stock data for all tickers
data = dict()
tickers = ["NVDA", "AMZN", "GOOG"]

for ticker in tickers:
    data[ticker] = StockData(ticker, start_date_str, end_date_str)

print("Starting portfolio simulation...")
print(f"Initial portfolio value: ${port.get_value(currtime):,.2f}")
print(f"Initial positions: {port.positions}")

# Track daily results
daily_results = []

# Loop through 60 days of Yahoo data
for i in range(60):
    # Move to next day
    currtime = currtime + timedelta(days=1)
    
    # Update current time for all stock data objects
    for ticker in tickers:
        data[ticker].curtime = currtime
    
    # Get current prices
    current_prices = {}
    for ticker in tickers:
        price = data[ticker].get_price()
        if price is not None:
            current_prices[ticker] = price
    
    # Check if conditions and execute trades
    trades_executed = []
    if "NVDA" in current_prices and current_prices["NVDA"] > 180:
        port.sell("NVDA", current_prices["NVDA"], 10, currtime)
    
    # Get current portfolio value
    current_value = port.get_value(currtime)
    
    # Store daily results
    daily_result = {
        'day': i + 1,
        'date': currtime,
        'prices': current_prices.copy(),
        'portfolio_value': current_value,
        'trades': trades_executed.copy(),
        'positions': port.positions.copy()
    }
    daily_results.append(daily_result)
    
    # Print results for this day
    print(f"\nDay {i+1} ({currtime.strftime('%Y-%m-%d')}):")
    print(f"  Prices: ", end="")
    for ticker, price in current_prices.items():
        print(f"{ticker}=${price:.2f} ", end="")
    print()
    
    
    time.sleep(0.4)  # Small delay after each trade
    
    print(f"  Portfolio Value: ${current_value:,.2f}")
    print(f"  Positions: {port.positions}")
    
    # Add a small delay between days
    time.sleep(0.5)

# Add delay before final summary
time.sleep(1.0)

# Final summary
print(f"\n" + "="*60)
print("FINAL PORTFOLIO SUMMARY")
print("="*60)
print(f"Final Portfolio Value: ${port.get_value(currtime):,.2f}")
print(f"Total P&L: ${port.get_PNL(currtime):,.2f}")
print(f"Final Positions: {port.positions}")
print(f"Total Trades: {len(port.past_trades)}")

# Calculate and display performance metrics
if len(daily_results) > 1:
    initial_value = daily_results[0]['portfolio_value']
    final_value = daily_results[-1]['portfolio_value']
    total_return = (final_value - initial_value) / initial_value * 100
    
    print(f"\nPerformance Metrics:")
    print(f"Total Return: {total_return:.2f}%")
    print(f"Days Simulated: {len(daily_results)}")
    
    # Calculate Sharpe ratio
    sharpe_ratio = port.calculate_sharpe_ratio()
    if sharpe_ratio is not None:
        print(f"Sharpe Ratio: {sharpe_ratio:.3f}")

# Add delay before plotting
time.sleep(1.0)
time.sleep(0.5)

# Plot portfolio performance
port.plot_portfolio_value("Portfolio Performance Over 60 Days")
port.plot_portfolio_value("Portfolio Performance (Percentage View)", show_percentage=True)
