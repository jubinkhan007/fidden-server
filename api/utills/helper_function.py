from math import radians, cos, sin, asin, sqrt
import re

def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two lat/lon points in kilometers."""
    R = 6371  # Earth radius in kilometers
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    distance_km = R * c
    return round(distance_km, 2)

# --- Helper: relevance scoring ---
def get_relevance(text, query):
    text_lower = text.lower()
    query_lower = query.lower()
    words = re.findall(r'\w+', text_lower)
    if any(query_lower in word for word in words):
        if text_lower == query_lower:
            return 1.0
        return 0.7
    return None

# --- Helper: check if any word contains query ---
def query_in_text_words(text, query):
    query_lower = query.lower()
    words = re.findall(r'\w+', text.lower())
    return any(query_lower in word for word in words)