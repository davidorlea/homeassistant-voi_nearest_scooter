"""Representation of VOI Nearest Scooter Sensors."""

from datetime import timedelta
import logging

from geopy.distance import distance
import requests
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_BATTERY_LEVEL,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_NAME,
    LENGTH_METERS,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
from homeassistant.util.json import load_json, save_json

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)

CONF_TOKEN_FILE = "token_file"

DEFAULT_NAME = "VOI Nearest Scooter"
DEFAULT_TOKEN_FILE = "voi-token.json"

ICON = "mdi:scooter"
ATTRIBUTION = "Data provided by VOI"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_TOKEN_FILE, default=DEFAULT_TOKEN_FILE): cv.string,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform."""
    name = config.get(CONF_NAME)
    token_path = hass.config.path(config.get(CONF_TOKEN_FILE))
    latitude = hass.config.latitude
    longitude = hass.config.longitude

    token_cache = load_json(token_path)
    if not token_cache or "authentication_token" not in token_cache:
        raise ValueError("Missing or bad token file.")

    add_entities([VoiNearestScooterSensor(name, token_path, latitude, longitude)])


class VoiNearestScooterApi:
    """Representation of the VOI API."""

    def __init__(self, token_path):
        """Initialize the VOI API."""
        self._accessToken = None
        self._tokenPath = token_path

    def __get_authentication_token(self):
        """Load the authentication token from the token file."""
        cache = load_json(self._tokenPath)
        return cache["authentication_token"]

    def __set_authentication_token(self, token):
        """Save the authentication token to the token file."""
        cache = {"authentication_token": token}
        save_json(self._tokenPath, cache)

    @staticmethod
    def __call(method, resource, headers=None, json=None):
        """Call the VOI API and parse the response as JSON."""
        result = requests.request(method, resource, headers=headers, json=json)

        if result:
            try:
                return result.json()
            except ValueError:
                pass

        _LOGGER.debug("Erroneous response (%s)", result)
        return result

    def __authenticate(self):
        """Authenticate to the VOI API."""
        body = {"authenticationToken": self.__get_authentication_token()}
        result = self.__call("POST", "https://api.voiapp.io/v1/auth/session", json=body)

        if result and "accessToken" in result and "authenticationToken" in result:
            self._accessToken = result["accessToken"]
            self.__set_authentication_token(result["authenticationToken"])
        else:
            _LOGGER.warning("Authentication failed: Erroneous response (%s)", result)

    def __request(self, method, resource, retry=True):
        """Issue an authenticated request to the VOI API."""
        headers = {"x-access-token": self._accessToken}
        result = self.__call(method, resource, headers=headers)

        if result:
            return result
        elif result.status_code == 401 and retry:
            self.__authenticate()
            return self.__request(method, resource, retry=False)
        else:
            raise requests.HTTPError(result)

    def get_zones(self, latitude, longitude):
        """Get the list of zones of geo coordinates from the VOI API."""
        result = self.__request(
            "GET",
            "https://api.voiapp.io/v1/zones?lat={}&lng={}".format(latitude, longitude),
        )
        if result and "zones" in result:
            return result["zones"]

    def get_vehicles(self, latitude, longitude):
        """Get the list of vehicles of a zone from the VOI API."""
        result = self.get_zones(latitude, longitude)
        if result and "zone_id" in result[0]:
            return self.__request(
                "GET",
                "https://api.voiapp.io/v1/vehicles/zone/{}/ready".format(
                    result[0]["zone_id"]
                ),
            )


class VoiNearestScooterSensor(Entity):
    """Representation of a VOI Nearest Scooter Sensor."""

    def __init__(self, name, token_path, latitude, longitude):
        """Initialize the VOI Nearest Scooter Sensor."""
        self._api = VoiNearestScooterApi(token_path)
        self._name = name
        self._latitude = latitude
        self._longitude = longitude
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the VOI Nearest Scooter Sensor."""
        return self._name

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the VOI Nearest Scooter Sensor."""
        return LENGTH_METERS

    @property
    def icon(self):
        """Icon to use in the frontend of the VOI Nearest Scooter Sensor."""
        return ICON

    @property
    def state(self):
        """Return the state of the VOI Nearest Scooter Sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the VOI Nearest Scooter Sensor."""
        return self._attributes

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Fetch new state data for the VOI Nearest Scooter Sensor."""
        self._state = None
        self._attributes = {}

        vehicles = self._api.get_vehicles(self._latitude, self._longitude)
        scooter = {}

        if vehicles:
            for vehicle in vehicles:
                location_vehicle = (vehicle["location"][0], vehicle["location"][1])
                location_hass = (self._latitude, self._longitude)
                vehicle["distance"] = distance(location_vehicle, location_hass).m

            scooter = sorted(vehicles, key=lambda item: item["distance"])[0]

        if scooter:
            self._state = round(scooter["distance"])
            self._attributes[ATTR_LATITUDE] = round(scooter["location"][0], 5)
            self._attributes[ATTR_LONGITUDE] = round(scooter["location"][1], 5)
            self._attributes[ATTR_BATTERY_LEVEL] = round(scooter["battery"])
            self._attributes[ATTR_ATTRIBUTION] = ATTRIBUTION
