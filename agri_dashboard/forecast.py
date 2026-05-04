"""
Forecasting module using Prophet for price predictions.
Generates 7-day forecasts for commodities prices.
"""

import pandas as pd
from prophet import Prophet
from database import get_historic_data
import warnings
warnings.filterwarnings('ignore')


def prepare_data_for_prophet(commodity=None, city=None):
    """
    Fetch historic data and prepare it for Prophet forecasting.
    
    Args:
        commodity: Optional filter for commodity type
        city: Optional filter for city
    
    Returns:
        pandas DataFrame with columns 'ds' (date) and 'y' (price)
    """
    data = get_historic_data(commodity=commodity, city=city)
    
    if not data:
        return None
    
    # Convert to DataFrame
    df = pd.DataFrame(data, columns=['timestamp', 'commodity', 'source', 'price', 'city', 'sentiment_score'])
    
    # Convert timestamp to datetime (handle mixed formats: with/without microseconds)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp'])

    # Group by date and take average price per day
    df['ds'] = df['timestamp'].dt.date
    daily_prices = df.groupby('ds')['price'].mean().reset_index()
    daily_prices.columns = ['ds', 'y']
    daily_prices['ds'] = pd.to_datetime(daily_prices['ds'])
    
    # Prophet requires at least 2 data points
    if len(daily_prices) < 2:
        return None
    
    return daily_prices


def generate_forecast(commodity=None, city=None, periods=7):
    """
    Generate price forecast using Prophet for the next N days.
    
    Args:
        commodity: Optional filter for commodity type
        city: Optional filter for city
        periods: Number of days to forecast (default 7)
    
    Returns:
        pandas DataFrame with forecast columns: ds, yhat, yhat_lower, yhat_upper
        Returns None if insufficient data
    """
    # Prepare data
    df = prepare_data_for_prophet(commodity=commodity, city=city)
    
    if df is None or len(df) < 2:
        print(f"Insufficient data for forecasting. Need at least 2 data points.")
        return None
    
    try:
        # Initialize and fit Prophet model
        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=False,
            changepoint_prior_scale=0.05  # Lower value for more conservative forecasts
        )
        
        model.fit(df)
        
        # Create future dataframe
        future = model.make_future_dataframe(periods=periods)
        
        # Generate forecast
        forecast = model.predict(future)
        
        # Return only the forecasted period (last N rows)
        forecast_result = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(periods)
        forecast_result.columns = ['date', 'forecasted_price', 'lower_bound', 'upper_bound']
        
        return forecast_result
    
    except Exception as e:
        print(f"Error generating forecast: {e}")
        return None


def get_forecast_with_history(commodity=None, city=None, periods=7):
    """
    Get forecast along with historical data for visualization.
    
    Returns:
        Tuple of (historical_df, forecast_df)
    """
    # Get historical data
    historical_df = prepare_data_for_prophet(commodity=commodity, city=city)
    
    if historical_df is None:
        return None, None
    
    # Get forecast
    forecast_df = generate_forecast(commodity=commodity, city=city, periods=periods)
    
    return historical_df, forecast_df
