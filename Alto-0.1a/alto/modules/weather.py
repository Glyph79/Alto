import requests
import json

def handle(text):
    """
    Get weather for the user's approximate location based on their IP address.
    Uses:
    - ip-api.com for free IP geolocation (no API key, rate-limited but fine for personal use)
    - Open-Meteo for free weather data (no API key required)
    """
    try:
        # Step 1: Get user's approximate location from their IP address
        location = get_location_from_ip()
        if not location:
            return "I couldn't determine your location. Please try again later."
        
        city = location.get('city', 'Unknown location')
        country = location.get('country', '')
        lat = location.get('lat')
        lon = location.get('lon')
        
        # Step 2: Get weather for those coordinates
        weather = get_weather(lat, lon)
        if not weather:
            return f"I found your location ({city}, {country}) but couldn't fetch the weather data."
        
        # Step 3: Format and return the response
        return format_weather_response(city, country, weather)
        
    except Exception as e:
        print(f"--- Weather module error: {e}")
        return "Sorry, I encountered an error while fetching the weather."

def get_location_from_ip():
    """
    Get approximate location from user's IP address using ip-api.com (free, no API key).
    Returns dict with city, country, lat, lon or None on failure.
    """
    try:
        # ip-api.com free endpoint - returns JSON with city, country, lat, lon
        response = requests.get('http://ip-api.com/json/', timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'success':
            return {
                'city': data.get('city', 'Unknown'),
                'country': data.get('country', ''),
                'lat': data.get('lat'),
                'lon': data.get('lon')
            }
        return None
    except Exception as e:
        print(f"--- Geolocation error: {e}")
        return None

def get_weather(lat, lon):
    """
    Get current weather for coordinates using Open-Meteo API (free, no API key).
    Returns dict with temperature, conditions, humidity, wind, etc.
    """
    try:
        # Open-Meteo free API - no key required
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
            "hourly": "temperature_2m,relativehumidity_2m,windspeed_10m",
            "timezone": "auto",
            "forecast_days": 1
        }
        
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # Extract current weather
        current = data.get('current_weather', {})
        
        # Get humidity from hourly data (first hour)
        humidity = None
        if 'hourly' in data and 'relativehumidity_2m' in data['hourly']:
            humidity = data['hourly']['relativehumidity_2m'][0]
        
        return {
            'temperature': current.get('temperature'),
            'windspeed': current.get('windspeed'),
            'winddirection': current.get('winddirection'),
            'humidity': humidity,
            'conditions': get_condition_description(current.get('weathercode', 0))
        }
    except Exception as e:
        print(f"--- Weather API error: {e}")
        return None

def get_condition_description(weathercode):
    """
    Convert WMO weather code to human-readable description.
    WMO codes reference: https://open-meteo.com/en/docs
    """
    weather_codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow fall",
        73: "Moderate snow fall",
        75: "Heavy snow fall",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail"
    }
    return weather_codes.get(weathercode, "Unknown conditions")

def format_weather_response(city, country, weather):
    """Format the weather data into a nice response string."""
    location_str = f"{city}, {country}" if country else city
    
    temp = weather.get('temperature')
    temp_unit = "°C"  # Open-Meteo uses Celsius by default
    
    conditions = weather.get('conditions', 'Unknown')
    
    # Build response
    response = f"Current weather in {location_str}: {conditions}. "
    
    if temp is not None:
        response += f"Temperature is {temp}{temp_unit}. "
    
    humidity = weather.get('humidity')
    if humidity is not None:
        response += f"Humidity: {humidity}%. "
    
    wind = weather.get('windspeed')
    if wind is not None:
        response += f"Wind speed: {wind} km/h."
    
    return response.strip()