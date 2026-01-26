"""
Main Streamlit dashboard for the Commodities Trading Dashboard.
Displays live rates, trends, and AI-powered forecasts.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import sys
import os

# Add the parent directory to path to import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import init_db, seed_data, get_todays_prices, get_historic_data
from forecast import generate_forecast, get_forecast_with_history
from analysis import get_latest_arbitrage_opportunities, get_arbitrage_summary
from news_engine import get_market_news, get_sentiment_summary

# Page configuration
st.set_page_config(
    page_title="Pakistan Commodities Trading Dashboard",
    page_icon="🌾",
    layout="wide"
)

# Initialize database on startup
if 'db_initialized' not in st.session_state:
    init_db()
    st.session_state.db_initialized = True


def main():
    """Main dashboard application."""
    
    # Title and header
    st.title("🌾 Pakistan Commodities Trading Dashboard")
    st.markdown("**Live Market Rates | Trends | AI Forecasts**")
    st.markdown("---")
    
    # Sidebar filters
    st.sidebar.header("📊 Filters")
    
    # Get unique commodities and cities from database
    from database import DB_PATH, get_connection
    try:
        conn = get_connection()
        df_all = pd.read_sql_query("SELECT DISTINCT commodity, city FROM market_data", conn)
        conn.close()
        
        commodities_list = ["All"] + sorted(df_all['commodity'].unique().tolist()) if not df_all.empty else ["All", "Cotton", "Wheat", "Corn"]
        cities_list = ["All"] + sorted(df_all['city'].unique().tolist()) if not df_all.empty else ["All", "Karachi", "Lahore", "Faisalabad", "Multan"]
    except Exception as e:
        # If table doesn't exist or query fails, use defaults
        commodities_list = ["All", "Cotton", "Wheat", "Corn"]
        cities_list = ["All", "Karachi", "Lahore", "Faisalabad", "Multan"]
    
    selected_commodity = st.sidebar.selectbox("Select Commodity", commodities_list)
    selected_city = st.sidebar.selectbox("Select City", cities_list)
    
    # Convert "All" to None for filtering
    commodity_filter = None if selected_commodity == "All" else selected_commodity
    city_filter = None if selected_city == "All" else selected_city
    
    # Seed data button (for testing)
    if st.sidebar.button("🌱 Seed Sample Data"):
        seed_data()
        st.sidebar.success("Sample data added! Refresh to see updates.")
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Note:** Use the seed button to add sample data for testing.")
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Live Rates", 
        "📊 Trends", 
        "🤖 AI Forecast",
        "💰 Arbitrage",
        "📰 Market Intelligence"
    ])
    
    # TAB 1: Live Rates
    with tab1:
        st.header("Today's Market Rates")
        
        try:
            # Get today's prices
            today_data = get_todays_prices()
            
            if today_data:
                # Convert to DataFrame
                df_today = pd.DataFrame(
                    today_data,
                    columns=['Timestamp', 'Commodity', 'Source', 'Price (PKR)', 'City', 'Sentiment', 'Raw Message']
                )
                
                # Apply filters
                if commodity_filter:
                    df_today = df_today[df_today['Commodity'] == commodity_filter]
                if city_filter:
                    df_today = df_today[df_today['City'] == city_filter]
                
                # Format timestamp
                df_today['Timestamp'] = pd.to_datetime(df_today['Timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
                
                # Display summary metrics
                if not df_today.empty:
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Total Records", len(df_today))
                    with col2:
                        avg_price = df_today['Price (PKR)'].mean()
                        st.metric("Avg Price (PKR)", f"Rs. {avg_price:,.2f}")
                    with col3:
                        max_price = df_today['Price (PKR)'].max()
                        st.metric("Max Price (PKR)", f"Rs. {max_price:,.2f}")
                    with col4:
                        min_price = df_today['Price (PKR)'].min()
                        st.metric("Min Price (PKR)", f"Rs. {min_price:,.2f}")
                    
                    st.markdown("---")
                
                # Display dataframe
                st.dataframe(
                    df_today[['Timestamp', 'Commodity', 'Price (PKR)', 'City', 'Source', 'Sentiment']],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No data available for today. Click 'Seed Sample Data' in the sidebar to add test data.")
        
        except Exception as e:
            st.error(f"Error loading today's rates: {e}")
    
    # TAB 2: Trends
    with tab2:
        st.header("Price Trends Over Time")
        
        try:
            # Get historic data
            historic_data = get_historic_data(commodity=commodity_filter, city=city_filter)
            
            if historic_data:
                df_historic = pd.DataFrame(
                    historic_data,
                    columns=['Timestamp', 'Commodity', 'Source', 'Price', 'City', 'Sentiment']
                )
                df_historic['Timestamp'] = pd.to_datetime(df_historic['Timestamp'])
                
                # Create interactive plot
                fig = go.Figure()
                
                # Group by commodity for different lines
                for commodity in df_historic['Commodity'].unique():
                    df_comm = df_historic[df_historic['Commodity'] == commodity].sort_values('Timestamp')
                    fig.add_trace(go.Scatter(
                        x=df_comm['Timestamp'],
                        y=df_comm['Price'],
                        mode='lines+markers',
                        name=commodity,
                        line=dict(width=2),
                        marker=dict(size=6)
                    ))
                
                fig.update_layout(
                    title="Price Trends by Commodity",
                    xaxis_title="Date",
                    yaxis_title="Price (PKR)",
                    hovermode='x unified',
                    height=500,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Summary statistics
                st.subheader("Summary Statistics")
                summary = df_historic.groupby('Commodity')['Price'].agg(['mean', 'min', 'max', 'std']).round(2)
                summary.columns = ['Average', 'Minimum', 'Maximum', 'Std Dev']
                st.dataframe(summary, use_container_width=True)
            else:
                st.info("No historical data available. Click 'Seed Sample Data' in the sidebar to add test data.")
        
        except Exception as e:
            st.error(f"Error loading trends: {e}")
    
    # TAB 3: AI Forecast
    with tab3:
        st.header("AI-Powered Price Forecast (Next 7 Days)")
        
        try:
            # Get forecast
            historical_df, forecast_df = get_forecast_with_history(
                commodity=commodity_filter,
                city=city_filter,
                periods=7
            )
            
            if forecast_df is not None and historical_df is not None:
                # Create forecast visualization
                fig = go.Figure()
                
                # Plot historical data
                fig.add_trace(go.Scatter(
                    x=historical_df['ds'],
                    y=historical_df['y'],
                    mode='lines+markers',
                    name='Historical Prices',
                    line=dict(color='blue', width=2),
                    marker=dict(size=6)
                ))
                
                # Plot forecast
                fig.add_trace(go.Scatter(
                    x=forecast_df['date'],
                    y=forecast_df['forecasted_price'],
                    mode='lines+markers',
                    name='Forecasted Price',
                    line=dict(color='green', width=2, dash='dash'),
                    marker=dict(size=8)
                ))
                
                # Plot confidence interval
                fig.add_trace(go.Scatter(
                    x=forecast_df['date'].tolist() + forecast_df['date'].tolist()[::-1],
                    y=forecast_df['upper_bound'].tolist() + forecast_df['lower_bound'].tolist()[::-1],
                    fill='toself',
                    fillcolor='rgba(0, 255, 0, 0.2)',
                    line=dict(color='rgba(255,255,255,0)'),
                    name='Confidence Interval',
                    showlegend=True
                ))
                
                fig.update_layout(
                    title="Price Forecast with Confidence Interval",
                    xaxis_title="Date",
                    yaxis_title="Price (PKR)",
                    hovermode='x unified',
                    height=500,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Display forecast table
                st.subheader("Forecast Details")
                forecast_display = forecast_df.copy()
                forecast_display['date'] = pd.to_datetime(forecast_display['date']).dt.strftime('%Y-%m-%d')
                forecast_display['forecasted_price'] = forecast_display['forecasted_price'].round(2)
                forecast_display['lower_bound'] = forecast_display['lower_bound'].round(2)
                forecast_display['upper_bound'] = forecast_display['upper_bound'].round(2)
                forecast_display.columns = ['Date', 'Forecasted Price (PKR)', 'Lower Bound (PKR)', 'Upper Bound (PKR)']
                
                st.dataframe(forecast_display, use_container_width=True, hide_index=True)
                
                # Forecast summary
                col1, col2, col3 = st.columns(3)
                with col1:
                    avg_forecast = forecast_df['forecasted_price'].mean()
                    st.metric("Avg Forecast (PKR)", f"Rs. {avg_forecast:,.2f}")
                with col2:
                    max_forecast = forecast_df['forecasted_price'].max()
                    st.metric("Max Forecast (PKR)", f"Rs. {max_forecast:,.2f}")
                with col3:
                    min_forecast = forecast_df['forecasted_price'].min()
                    st.metric("Min Forecast (PKR)", f"Rs. {min_forecast:,.2f}")
            else:
                st.warning("Insufficient data for forecasting. Need at least 2 data points. Click 'Seed Sample Data' in the sidebar to add test data.")
        
        except Exception as e:
            st.error(f"Error generating forecast: {e}")
            import traceback
            st.code(traceback.format_exc())
    
    # TAB 4: Arbitrage Opportunities
    with tab4:
        st.header("💰 Arbitrage Opportunities")
        st.markdown("**Find profitable trading opportunities between cities**")
        
        try:
            # Get arbitrage opportunities
            opportunities_df = get_latest_arbitrage_opportunities(min_profit_margin=0.05)
            
            if not opportunities_df.empty:
                # Display summary metrics
                summary = get_arbitrage_summary()
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Opportunities", summary['total_opportunities'])
                with col2:
                    st.metric("Avg Profit Margin", f"{summary['avg_profit_margin']}%")
                with col3:
                    st.metric("Max Profit Margin", f"{summary['max_profit_margin']}%")
                with col4:
                    st.metric("Best Route", summary['best_route'] or "N/A")
                
                st.markdown("---")
                
                # Display opportunities table with styling
                st.subheader("High Profit Opportunities")
                
                # Format the dataframe for display
                display_df = opportunities_df.copy()
                display_df['date'] = pd.to_datetime(display_df['date']).dt.strftime('%Y-%m-%d')
                display_df = display_df.rename(columns={
                    'commodity': 'Commodity',
                    'date': 'Date',
                    'buy_city': 'Buy City',
                    'sell_city': 'Sell City',
                    'buy_price': 'Buy Price (PKR)',
                    'sell_price': 'Sell Price (PKR)',
                    'price_difference': 'Price Difference (PKR)',
                    'profit_margin': 'Profit Margin (%)',
                    'profit_amount': 'Profit/Unit (PKR)'
                })
                
                # Display with color coding for profit margin
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Highlight high-profit opportunities
                high_profit = opportunities_df[opportunities_df['profit_margin'] >= 10]
                if not high_profit.empty:
                    st.success(f"🚀 **{len(high_profit)} High-Profit Opportunities** (≥10% margin) detected!")
            else:
                st.info("No arbitrage opportunities found. Try seeding more sample data with different cities and prices.")
                st.markdown("**Tip:** Arbitrage opportunities appear when price differences between cities exceed 5% (to cover transport costs).")
        
        except Exception as e:
            st.error(f"Error analyzing arbitrage opportunities: {e}")
            import traceback
            st.code(traceback.format_exc())
    
    # TAB 5: Market Intelligence
    with tab5:
        st.header("📰 Market Intelligence & News Sentiment")
        st.markdown("**Real-time news analysis with AI-powered sentiment scoring**")
        
        try:
            # Get sentiment summary
            sentiment_summary = get_sentiment_summary()
            
            # Display overall sentiment metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                sentiment_color = "🟢" if sentiment_summary['overall_sentiment'] == 'Bullish' else "🔴" if sentiment_summary['overall_sentiment'] == 'Bearish' else "⚪"
                st.metric("Overall Sentiment", f"{sentiment_color} {sentiment_summary['overall_sentiment']}")
            with col2:
                st.metric("Avg Sentiment Score", f"{sentiment_summary['avg_sentiment']:.3f}")
            with col3:
                st.metric("Bullish News", f"{sentiment_summary['bullish_count']} 📈")
            with col4:
                st.metric("Bearish News", f"{sentiment_summary['bearish_count']} 📉")
            
            st.markdown("---")
            
            # Get and display news headlines
            news_items = get_market_news(num_headlines=10)
            
            st.subheader("Latest Market News")
            
            for item in news_items:
                # Create columns for layout
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    st.markdown(f"**{item['headline']}**")
                
                with col2:
                    # Color-coded sentiment badge
                    if item['sentiment_label'] == 'Bullish':
                        st.success(f"🟢 {item['sentiment_label']}")
                    elif item['sentiment_label'] == 'Bearish':
                        st.error(f"🔴 {item['sentiment_label']}")
                    else:
                        st.info(f"⚪ {item['sentiment_label']}")
                
                # Show sentiment score and signal
                score = item['sentiment_score']
                if score > 0.1:
                    st.markdown(f"📊 **Sentiment Score:** `{score:.3f}` | ✅ **Signal:** Bullish - Market Optimistic")
                elif score < -0.1:
                    st.markdown(f"📊 **Sentiment Score:** `{score:.3f}` | ⚠️ **Signal:** Bearish - Market Concerns")
                else:
                    st.markdown(f"📊 **Sentiment Score:** `{score:.3f}` | ➖ **Signal:** Neutral - No Strong Direction")
                
                st.markdown("---")
            
            # Filter by commodity
            st.subheader("Filter News by Commodity")
            commodity_filter_news = st.selectbox(
                "Select Commodity",
                ["All", "Cotton", "Wheat", "Corn"],
                key="news_filter"
            )
            
            if commodity_filter_news != "All":
                filtered_news = [item for item in news_items if commodity_filter_news.lower() in item['headline'].lower()]
                if filtered_news:
                    st.info(f"Found {len(filtered_news)} news items related to {commodity_filter_news}")
                    for item in filtered_news:
                        st.markdown(f"- **{item['headline']}** ({item['sentiment_label']})")
                else:
                    st.warning(f"No specific news found for {commodity_filter_news}. Showing all news above.")
        
        except Exception as e:
            st.error(f"Error loading market intelligence: {e}")
            import traceback
            st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
