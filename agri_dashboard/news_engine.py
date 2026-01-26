"""
News sentiment analysis engine for the Commodities Trading Dashboard.
Analyzes news headlines for market sentiment using TextBlob (with fallback).
"""

from datetime import datetime
import random

# Try to import TextBlob, fallback to simple keyword-based analysis if not available
try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    print("Warning: TextBlob not available. Using keyword-based sentiment analysis.")


# Realistic Pakistan commodity market news headlines
# Based on typical market news patterns (using mock data as requested)
MOCK_NEWS_HEADLINES = [
    "Pakistan Cotton Prices Surge 15% Amid Export Demand Increase",
    "FBR Imposes 5% Tax on Wheat Imports, Local Prices Expected to Rise",
    "Corn Production Drops 20% Due to Water Shortage in Punjab",
    "Government Announces Subsidy for Cotton Farmers, Market Optimistic",
    "Wheat Procurement Target Missed by 30%, Shortage Concerns Grow",
    "Cotton Export Ban Lifted, International Buyers Show Strong Interest",
    "FBR Tax Relief on Agricultural Commodities Extended for 6 Months",
    "Wheat Prices Hit Record High in Karachi, Traders See Bullish Trend",
    "Corn Futures Decline on Global Market Pressure, Local Impact Minimal",
    "Pakistan Cotton Quality Improves, Premium Prices Expected This Season"
]


def calculate_sentiment(text):
    """
    Calculate sentiment polarity using TextBlob (or keyword-based fallback).
    
    Args:
        text: The text to analyze
    
    Returns:
        float: Sentiment polarity score (-1.0 to 1.0)
        - Negative values indicate bearish sentiment
        - Positive values indicate bullish sentiment
        - Near zero indicates neutral sentiment
    """
    if TEXTBLOB_AVAILABLE:
        try:
            blob = TextBlob(text)
            return blob.sentiment.polarity
        except Exception:
            # Fallback if TextBlob fails
            pass
    
    # Keyword-based sentiment analysis (fallback)
    text_lower = text.lower()
    
    # Bullish keywords (positive sentiment)
    bullish_keywords = [
        'surge', 'increase', 'rise', 'up', 'growth', 'optimistic', 'strong',
        'premium', 'improve', 'demand', 'export', 'subsidy', 'relief',
        'bullish', 'gain', 'profit', 'success', 'high', 'record'
    ]
    
    # Bearish keywords (negative sentiment)
    bearish_keywords = [
        'drop', 'decline', 'fall', 'down', 'decrease', 'shortage', 'concern',
        'miss', 'ban', 'pressure', 'low', 'worst', 'crisis', 'problem',
        'bearish', 'loss', 'fail', 'risk', 'warning', 'tax'
    ]
    
    bullish_count = sum(1 for word in bullish_keywords if word in text_lower)
    bearish_count = sum(1 for word in bearish_keywords if word in text_lower)
    
    # Calculate sentiment score
    total_keywords = bullish_count + bearish_count
    if total_keywords == 0:
        return 0.0  # Neutral
    
    # Normalize to -1 to 1 range
    sentiment = (bullish_count - bearish_count) / max(total_keywords, 1)
    return max(-1.0, min(1.0, sentiment * 0.8))  # Scale slightly to avoid extremes


def get_market_news(num_headlines=10):
    """
    Get market news headlines with sentiment analysis.
    
    Args:
        num_headlines: Number of headlines to return (default 10)
    
    Returns:
        List of dictionaries with:
        - headline: News headline text
        - sentiment_score: Sentiment polarity (-1 to 1)
        - sentiment_label: "Bullish", "Bearish", or "Neutral"
        - timestamp: Current timestamp
        - color: Color indicator for UI ("green", "red", "gray")
    """
    # Select random headlines (or all if less than requested)
    selected_headlines = random.sample(
        MOCK_NEWS_HEADLINES,
        min(num_headlines, len(MOCK_NEWS_HEADLINES))
    )
    
    news_items = []
    for headline in selected_headlines:
        sentiment_score = calculate_sentiment(headline)
        
        # Classify sentiment
        if sentiment_score > 0.1:
            sentiment_label = "Bullish"
            color = "green"
        elif sentiment_score < -0.1:
            sentiment_label = "Bearish"
            color = "red"
        else:
            sentiment_label = "Neutral"
            color = "gray"
        
        news_items.append({
            'headline': headline,
            'sentiment_score': round(sentiment_score, 3),
            'sentiment_label': sentiment_label,
            'timestamp': datetime.now(),
            'color': color
        })
    
    # Sort by sentiment score (most positive first)
    news_items.sort(key=lambda x: x['sentiment_score'], reverse=True)
    
    return news_items


def get_sentiment_summary():
    """
    Get overall market sentiment summary.
    
    Returns:
        Dictionary with sentiment statistics
    """
    news_items = get_market_news()
    
    if not news_items:
        return {
            'avg_sentiment': 0.0,
            'bullish_count': 0,
            'bearish_count': 0,
            'neutral_count': 0,
            'overall_sentiment': 'Neutral'
        }
    
    avg_sentiment = sum(item['sentiment_score'] for item in news_items) / len(news_items)
    bullish_count = sum(1 for item in news_items if item['sentiment_label'] == 'Bullish')
    bearish_count = sum(1 for item in news_items if item['sentiment_label'] == 'Bearish')
    neutral_count = sum(1 for item in news_items if item['sentiment_label'] == 'Neutral')
    
    if avg_sentiment > 0.1:
        overall = 'Bullish'
    elif avg_sentiment < -0.1:
        overall = 'Bearish'
    else:
        overall = 'Neutral'
    
    return {
        'avg_sentiment': round(avg_sentiment, 3),
        'bullish_count': bullish_count,
        'bearish_count': bearish_count,
        'neutral_count': neutral_count,
        'overall_sentiment': overall
    }


def get_commodity_specific_news(commodity):
    """
    Filter news headlines relevant to a specific commodity.
    
    Args:
        commodity: Commodity name (Cotton, Wheat, Corn)
    
    Returns:
        List of filtered news items
    """
    all_news = get_market_news()
    
    # Filter by commodity keyword
    filtered = [
        item for item in all_news
        if commodity.lower() in item['headline'].lower()
    ]
    
    return filtered if filtered else all_news[:3]  # Return top 3 if no matches
