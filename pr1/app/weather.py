import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 5.0


class WeatherError(Exception):
    pass


class CityNotFoundError(WeatherError):
    pass


class ApiServiceError(WeatherError):
    pass


def find_city(name: str) -> dict:
    name = name.strip()
    if not name:
        raise WeatherError("Назва міста не може бути порожньою")

    try:
        response = requests.get(
            GEOCODING_URL,
            params={"name": name, "count": 1, "language": "uk", "format": "json"},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        raise ApiServiceError("Сервіс геокодування недоступний")

    if response.status_code >= 500:
        raise ApiServiceError("Помилка на боці сервера геокодування")
    elif response.status_code >= 400:
        raise WeatherError("Некоректний запит до сервісу геокодування")

    try:
        data = response.json()
    except ValueError:
        raise ApiServiceError("Некоректна відповідь від сервісу геокодування")

    results = data.get("results")
    if not results:
        raise CityNotFoundError(f"Місто '{name}' не знайдено")

    city_data = results[0]
    return {
        "name": city_data.get("name", name),
        "country": city_data.get("country", ""),
        "latitude": city_data["latitude"],
        "longitude": city_data["longitude"],
    }


def get_current_weather(city: str) -> dict:
    city_info = find_city(city)

    try:
        response = requests.get(
            FORECAST_URL,
            params={
                "latitude": city_info["latitude"],
                "longitude": city_info["longitude"],
                "current": ["temperature_2m", "wind_speed_10m"],
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        raise ApiServiceError("Сервіс погоди недоступний")

    if response.status_code >= 500:
        raise ApiServiceError("Помилка на боці сервера погоди")
    elif response.status_code >= 400:
        raise WeatherError("Некоректний запит до сервісу погоди")

    try:
        data = response.json()
    except ValueError:
        raise ApiServiceError("Некоректна відповідь від сервісу погоди")

    current = data.get("current")
    units = data.get("current_units", {})

    if not current or "temperature_2m" not in current or "wind_speed_10m" not in current:
        raise ApiServiceError("У відповіді сервісу відсутні дані про погоду")

    return {
        "city": city_info["name"],
        "country": city_info["country"],
        "temperature": current["temperature_2m"],
        "temperature_unit": units.get("temperature_2m", "°C"),
        "wind_speed": current["wind_speed_10m"],
        "wind_speed_unit": units.get("wind_speed_10m", "km/h"),
    }