from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from cachetools import TTLCache
import requests
import time

app = FastAPI(title="Real Weather API", version="3.0")

# ----- Root Route -----
@app.get("/")
async def root():
    return {
        "message": "Welcome to the Real Weather API! Use /weather?cities=London,Mumbai,... to get weather data."
    }

# ----- Cache: store up to 100 results, TTL 120 sec -----
weather_cache = TTLCache(maxsize=100, ttl=120)

# ----- Rate limiting: 10 requests/minute per IP -----
RATE_LIMIT = 10
RATE_WINDOW = 60
rate_limit_store = {}

def is_rate_limited(ip: str) -> bool:
    current_time = time.time()
    request_times = rate_limit_store.get(ip, [])
    request_times = [t for t in request_times if current_time - t < RATE_WINDOW]
    rate_limit_store[ip] = request_times
    if len(request_times) >= RATE_LIMIT:
        return True
    rate_limit_store[ip].append(current_time)
    return False

# ----- City coordinates -----
city_coords = {
    "london": (51.5072, -0.1276),
    "mumbai": (19.0760, 72.8777),
    "new york": (40.7128, -74.0060),
    "paris": (48.8566, 2.3522),
    "tokyo": (35.6762, 139.6503),
    "dubai": (25.276987, 55.296249),
    "delhi": (28.6139, 77.2090),
    "berlin": (52.5200, 13.4050),
    "sydney": (-33.8688, 151.2093),
    "toronto": (43.65107, -79.347015),
}

# ----- Fetch weather from Open-Meteo -----
def fetch_weather(city: str):
    if city.lower() not in city_coords:
        raise HTTPException(status_code=404, detail=f"City '{city}' not found")
    lat, lon = city_coords[city.lower()]
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    res = requests.get(url)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch data from Open-Meteo")
    data = res.json().get("current_weather", {})
    return {
        "city": city.title(),
        "temperature": data.get("temperature"),
        "windspeed": data.get("windspeed"),
        "weathercode": data.get("weathercode"),
        "time": data.get("time"),
    }

# ----- Weather Endpoint -----
@app.get("/weather")
async def get_weather(request: Request, cities: str = "London,Mumbai,Tokyo", page: int = 1, limit: int = 3):
    client_ip = request.client.host
    if is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")

    cache_key = f"{cities}_{page}_{limit}"
    if cache_key in weather_cache:
        return {"source": "cache", "data": weather_cache[cache_key]}

    city_list = [c.strip() for c in cities.split(",") if c.strip()]
    results = []
    for city in city_list:
        try:
            results.append(fetch_weather(city))
        except HTTPException as e:
            results.append({"city": city.title(), "error": e.detail})

    # Pagination
    start = (page - 1) * limit
    end = start + limit
    paginated = results[start:end]

    weather_cache[cache_key] = paginated
    return {"source": "live", "data": paginated}

# ----- Error Handler -----
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

# ----- Run Server -----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
