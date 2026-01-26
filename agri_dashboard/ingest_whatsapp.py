"""
WhatsApp data ingestion script for the Commodities Trading Dashboard.
Fetches messages from UltraMsg API and extracts commodity price information.
"""

import requests
import re
from datetime import datetime
from database import insert_market_data, init_db
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# UltraMsg API configuration
ULTRAMSG_API_URL = os.getenv("ULTRAMSG_API_URL", "")
ULTRAMSG_API_KEY = os.getenv("ULTRAMSG_API_KEY", "")
ULTRAMSG_INSTANCE_ID = os.getenv("ULTRAMSG_INSTANCE_ID", "")


def extract_price_from_message(message, commodity_keywords):
    """
    Extract price information from a WhatsApp message using regex.
    
    Args:
        message: The raw message text
        commodity_keywords: List of commodity keywords to search for
    
    Returns:
        Tuple of (commodity, price) if found, else (None, None)
    """
    message_lower = message.lower()
    
    # Check for commodity keywords
    commodity = None
    for keyword in commodity_keywords:
        if keyword.lower() in message_lower:
            commodity = keyword
            break
    
    if not commodity:
        return None, None
    
    # Pattern to find prices: numbers near keywords like "Rate", "Price", "Rs", "PKR"
    # Matches patterns like: "Rate: 8500", "Price Rs 9000", "PKR 10000", etc.
    price_patterns = [
        r'(?:rate|price|rs|pkr)[\s:]*([\d,]+\.?\d*)',  # Rate: 8500 or Price Rs 9000
        r'([\d,]+\.?\d*)[\s]*(?:per|maund|kg|40kg)',  # 8500 per maund
        r'rs\.?\s*([\d,]+\.?\d*)',  # Rs. 8500
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                price = float(price_str)
                return commodity, price
            except ValueError:
                continue
    
    return None, None


def extract_city_from_message(message):
    """
    Extract city name from message.
    Common Pakistan cities for commodities trading.
    """
    cities = ["Karachi", "Lahore", "Faisalabad", "Multan", "Hyderabad", 
              "Rawalpindi", "Islamabad", "Peshawar", "Quetta", "Sialkot"]
    
    for city in cities:
        if city.lower() in message.lower():
            return city
    
    return "Unknown"


def fetch_whatsapp_messages():
    """
    Fetch messages from UltraMsg API.
    Returns list of messages or None if API fails.
    """
    if not ULTRAMSG_API_KEY or not ULTRAMSG_INSTANCE_ID:
        print("UltraMsg API credentials not configured. Using mock data.")
        return None
    
    try:
        # UltraMsg API endpoint (adjust based on actual API documentation)
        url = f"{ULTRAMSG_API_URL}/messages"
        headers = {
            "Authorization": f"Bearer {ULTRAMSG_API_KEY}",
            "Content-Type": "application/json"
        }
        params = {
            "instance_id": ULTRAMSG_INSTANCE_ID,
            "limit": 50  # Fetch last 50 messages
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        messages = data.get("messages", [])
        return messages
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from UltraMsg API: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


def generate_mock_data():
    """
    Generate mock WhatsApp messages for testing when API is unavailable.
    Returns a list of mock message dictionaries.
    """
    commodities = ["Cotton", "Wheat", "Corn"]
    cities = ["Karachi", "Lahore", "Faisalabad", "Multan"]
    sources = ["WhatsApp Group 1", "WhatsApp Group 2", "Market Updates"]
    
    mock_messages = []
    for i in range(10):
        commodity = commodities[i % len(commodities)]
        city = cities[i % len(cities)]
        source = sources[i % len(sources)]
        
        if commodity == "Cotton":
            price = 8500 + (i * 200)
        elif commodity == "Wheat":
            price = 3500 + (i * 100)
        else:
            price = 2800 + (i * 80)
        
        message = f"{commodity} rate in {city}: Rs. {price} per maund. Market is stable."
        mock_messages.append({
            "body": message,
            "from": source,
            "timestamp": datetime.now().isoformat()
        })
    
    return mock_messages


def ingest_data():
    """
    Main function to ingest WhatsApp data and store in database.
    Uses API if available, otherwise falls back to mock data.
    """
    print("Starting data ingestion...")
    
    # Initialize database if needed
    init_db()
    
    # Try to fetch from API
    messages = fetch_whatsapp_messages()
    
    # Fall back to mock data if API fails
    if messages is None:
        print("Using mock data for testing...")
        messages = generate_mock_data()
    
    # Process messages
    commodity_keywords = ["Cotton", "Wheat", "Corn"]
    processed_count = 0
    
    for message_data in messages:
        # Extract message text (adjust based on actual API response structure)
        if isinstance(message_data, dict):
            message_text = message_data.get("body", "") or message_data.get("message", "")
            source = message_data.get("from", "") or message_data.get("source", "Unknown")
        else:
            message_text = str(message_data)
            source = "Unknown"
        
        # Extract commodity and price
        commodity, price = extract_price_from_message(message_text, commodity_keywords)
        
        if commodity and price:
            city = extract_city_from_message(message_text)
            timestamp = datetime.now()
            
            # Simple sentiment score (can be enhanced with NLP later)
            sentiment_score = 0.0
            if any(word in message_text.lower() for word in ["up", "rise", "increase", "good"]):
                sentiment_score = 0.5
            elif any(word in message_text.lower() for word in ["down", "fall", "decrease", "bad"]):
                sentiment_score = -0.5
            
            # Insert into database
            insert_market_data(
                timestamp=timestamp,
                commodity=commodity,
                source=source,
                price=price,
                city=city,
                sentiment_score=sentiment_score,
                raw_message=message_text
            )
            processed_count += 1
            print(f"Processed: {commodity} - {city} - Rs. {price}")
    
    print(f"Data ingestion complete! Processed {processed_count} records.")


if __name__ == "__main__":
    ingest_data()
