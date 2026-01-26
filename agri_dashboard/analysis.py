"""
Arbitrage analysis module for the Commodities Trading Dashboard.
Identifies profitable trading opportunities between cities.
"""

import pandas as pd
from datetime import datetime, timedelta
from database import get_historic_data, get_connection
import sqlite3


def check_arbitrage(market_data=None, min_profit_margin=0.05):
    """
    Analyze market data to find arbitrage opportunities between cities.
    
    An arbitrage opportunity exists when the price difference between two cities
    exceeds the minimum profit margin (default 5% to cover transport costs).
    
    Args:
        market_data: Optional list of tuples from database. If None, fetches from DB.
        min_profit_margin: Minimum profit margin as decimal (0.05 = 5%)
    
    Returns:
        pandas DataFrame with arbitrage opportunities containing:
        - commodity: The commodity name
        - date: The date of the opportunity
        - buy_city: City with lower price (buy here)
        - sell_city: City with higher price (sell here)
        - buy_price: Price in buy_city
        - sell_price: Price in sell_city
        - price_difference: Absolute price difference
        - profit_margin: Percentage profit margin
        - profit_amount: Profit per unit
    """
    # Fetch data if not provided
    if market_data is None:
        market_data = get_historic_data()
    
    if not market_data:
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(
        market_data,
        columns=['timestamp', 'commodity', 'source', 'price', 'city', 'sentiment']
    )
    
    # Convert timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date
    
    # Group by commodity and date, then find price differences between cities
    opportunities = []
    
    for commodity in df['commodity'].unique():
        df_comm = df[df['commodity'] == commodity]
        
        for date in df_comm['date'].unique():
            df_date = df_comm[df_comm['date'] == date]
            
            # Get average price per city for this date
            city_prices = df_date.groupby('city')['price'].mean().sort_values()
            
            if len(city_prices) < 2:
                continue  # Need at least 2 cities for arbitrage
            
            # Compare all city pairs
            cities = city_prices.index.tolist()
            for i in range(len(cities)):
                for j in range(i + 1, len(cities)):
                    buy_city = cities[i]
                    sell_city = cities[j]
                    buy_price = city_prices.iloc[i]
                    sell_price = city_prices.iloc[j]
                    
                    # Calculate profit margin
                    price_diff = sell_price - buy_price
                    profit_margin = price_diff / buy_price
                    
                    # Check if opportunity meets minimum margin
                    if profit_margin >= min_profit_margin:
                        opportunities.append({
                            'commodity': commodity,
                            'date': date,
                            'buy_city': buy_city,
                            'sell_city': sell_city,
                            'buy_price': round(buy_price, 2),
                            'sell_price': round(sell_price, 2),
                            'price_difference': round(price_diff, 2),
                            'profit_margin': round(profit_margin * 100, 2),  # As percentage
                            'profit_amount': round(price_diff, 2)
                        })
    
    if not opportunities:
        return pd.DataFrame()
    
    # Convert to DataFrame and sort by profit margin (highest first)
    df_opportunities = pd.DataFrame(opportunities)
    df_opportunities = df_opportunities.sort_values('profit_margin', ascending=False)
    
    return df_opportunities


def get_latest_arbitrage_opportunities(min_profit_margin=0.05, days_back=7):
    """
    Get arbitrage opportunities from recent data.
    
    Args:
        min_profit_margin: Minimum profit margin (default 5%)
        days_back: Number of days to look back (default 7)
    
    Returns:
        DataFrame with latest arbitrage opportunities
    """
    # Get recent data
    conn = get_connection()
    cutoff_date = (datetime.now() - timedelta(days=days_back)).date()
    
    query = """
        SELECT timestamp, commodity, source, price, city, sentiment_score
        FROM market_data
        WHERE DATE(timestamp) >= ?
        ORDER BY timestamp DESC
    """
    
    recent_data = conn.execute(query, (cutoff_date,)).fetchall()
    conn.close()
    
    return check_arbitrage(recent_data, min_profit_margin)


def get_arbitrage_summary():
    """
    Get summary statistics of arbitrage opportunities.
    
    Returns:
        Dictionary with summary metrics
    """
    opportunities = get_latest_arbitrage_opportunities()
    
    if opportunities.empty:
        return {
            'total_opportunities': 0,
            'avg_profit_margin': 0,
            'max_profit_margin': 0,
            'best_commodity': None,
            'best_route': None
        }
    
    return {
        'total_opportunities': len(opportunities),
        'avg_profit_margin': round(opportunities['profit_margin'].mean(), 2),
        'max_profit_margin': round(opportunities['profit_margin'].max(), 2),
        'best_commodity': opportunities.iloc[0]['commodity'],
        'best_route': f"{opportunities.iloc[0]['buy_city']} → {opportunities.iloc[0]['sell_city']}"
    }
