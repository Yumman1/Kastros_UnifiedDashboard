"""
Database handling module for the Commodities Trading Dashboard.
Manages SQLite database operations for market data storage.
"""

import sqlite3
import os
from datetime import datetime, timedelta
import random

# Get the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "market_data.db")


def init_db():
    """
    Initialize the SQLite database and create the market_data table.
    Creates the database file if it doesn't exist.
    """
    # Ensure the directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create market_data table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            commodity TEXT NOT NULL,
            source TEXT NOT NULL,
            price REAL NOT NULL,
            city TEXT NOT NULL,
            sentiment_score REAL DEFAULT 0.0,
            raw_message TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


def seed_data():
    """
    Insert 5 fake records into the market_data table for testing.
    Creates records with realistic Pakistan market data.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Sample data for Pakistan commodities market
    commodities = ["Cotton", "Wheat", "Corn"]
    cities = ["Karachi", "Lahore", "Faisalabad", "Multan", "Hyderabad"]
    sources = ["WhatsApp Group 1", "WhatsApp Group 2", "Market Updates"]
    
    # Generate 5 records with dates spread over the last few days
    base_date = datetime.now()
    
    for i in range(5):
        timestamp = base_date - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))
        commodity = random.choice(commodities)
        city = random.choice(cities)
        source = random.choice(sources)
        
        # Realistic price ranges for Pakistan market (in PKR per maund/40kg)
        if commodity == "Cotton":
            price = round(random.uniform(8000, 12000), 2)
        elif commodity == "Wheat":
            price = round(random.uniform(3000, 4500), 2)
        else:  # Corn
            price = round(random.uniform(2500, 3500), 2)
        
        sentiment_score = round(random.uniform(-1.0, 1.0), 2)
        raw_message = f"{commodity} rate in {city}: Rs. {price} per maund"
        
        cursor.execute("""
            INSERT INTO market_data 
            (timestamp, commodity, source, price, city, sentiment_score, raw_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, commodity, source, price, city, sentiment_score, raw_message))
    
    conn.commit()
    conn.close()
    print("5 fake records inserted successfully!")


def get_connection():
    """Return a database connection."""
    return sqlite3.connect(DB_PATH)


def insert_market_data(timestamp, commodity, source, price, city, sentiment_score=0.0, raw_message=""):
    """
    Insert a new market data record into the database.
    
    Args:
        timestamp: DateTime object
        commodity: String (Cotton, Wheat, Corn)
        source: String (WhatsApp Group Name)
        price: Float
        city: String
        sentiment_score: Float (default 0.0)
        raw_message: String
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO market_data 
        (timestamp, commodity, source, price, city, sentiment_score, raw_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, commodity, source, price, city, sentiment_score, raw_message))
    
    conn.commit()
    conn.close()


def get_todays_prices():
    """
    Fetch all prices from today.
    Returns a list of tuples.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    today = datetime.now().date()
    cursor.execute("""
        SELECT timestamp, commodity, source, price, city, sentiment_score, raw_message
        FROM market_data
        WHERE DATE(timestamp) = DATE(?)
        ORDER BY timestamp DESC
    """, (today,))
    
    results = cursor.fetchall()
    conn.close()
    return results


def get_historic_data(commodity=None, city=None):
    """
    Fetch historic market data with optional filters.
    
    Args:
        commodity: Optional filter for commodity type
        city: Optional filter for city
    
    Returns:
        List of tuples with all matching records
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT timestamp, commodity, source, price, city, sentiment_score FROM market_data WHERE 1=1"
    params = []
    
    if commodity:
        query += " AND commodity = ?"
        params.append(commodity)
    
    if city:
        query += " AND city = ?"
        params.append(city)
    
    query += " ORDER BY timestamp ASC"
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return results
