import homeassistant.helpers.config_validation as cv
import json
import logging
import voluptuous as vol

from geopy.exc import (
    GeocoderTimedOut, GeocoderUnavailable
)
from geopy.distance import distance

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.components.rest.sensor import RestData
from homeassistant.const import (
    ATTR_ATTRIBUTION, CONF_NAME
)
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

ATTR_LATITUDE = 'latitude'
ATTR_LONGITUDE = 'longitude'
ATTR_BATTERY = 'battery'
ATTR_UPDATED = 'updated'

DEFAULT_NAME = 'VOI Nearest Scooter'

UNIT_OF_MEASUREMENT = 'm'
ICON = 'mdi:scooter'
ATTRIBUTION = 'Data provided by VOI'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
})

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Setup the sensor platform."""

    name = config.get(CONF_NAME)
    latitude = hass.config.latitude
    longitude = hass.config.longitude

    url = 'https://api.voiapp.io/v1/vehicle/status/ready?lat={}&lng={}'
    endpoint = url.format(latitude, longitude)
    rest = RestData('GET', endpoint, None, None, None, True)

    add_entities([VoiNearestScooterSensor(rest, name, latitude, longitude)])

class VoiNearestScooterSensor(Entity):
    """Representation of a VOI Nearest Scooter Sensor."""

    def __init__(self, rest, name, latitude, longitude):
        """Initialize the VOI Nearest Scooter Sensor."""
        self.rest = rest
        self._name = name
        self._latitude = latitude
        self._longitude = longitude
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the VOI Nearest Scooter Sensor."""
        return '{}'.format(self._name)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the VOI Nearest Scooter Sensor."""
        return UNIT_OF_MEASUREMENT

    @property
    def icon(self):
        """Icon to use in the frontend of the VOI Nearest Scooter Sensor."""
        return ICON

    @property
    def state(self):
        """Return the state of the VOI Nearest Scooter Sensor."""
        return self._state

    @property
    def device_state_attributes(self):
        """Return the state attributes of the VOI Nearest Scooter Sensor.."""
        return self._attributes

    def update(self):
        """Fetch new state data for the VOI Nearest Scooter Sensor."""
        self._state = None
        self._attributes = {}

        self.rest.update()
        result = self.rest.data
        scooter = {}

        if result:
            try:
                json_list = json.loads(result)

                for item in json_list:
                    item['distance'] = distance((item['location'][0], item['location'][1]), (self._latitude, self._longitude)).m

                scooter = sorted(json_list, key=lambda item: item['distance'])[0]

                _LOGGER.debug("Using JSON entry: %s", scooter)
            except ValueError:
                _LOGGER.warning("REST result could not be parsed as JSON")
                _LOGGER.debug("Erroneous JSON: %s", result)
        else:
            _LOGGER.warning("Empty reply found when expecting JSON data")

        if scooter:
            self._state = round(scooter['distance'])
            self._attributes[ATTR_LATITUDE] = round(scooter['location'][0], 5)
            self._attributes[ATTR_LONGITUDE] = round(scooter['location'][1], 5)
            self._attributes[ATTR_BATTERY] = round(scooter['battery'])
            self._attributes[ATTR_UPDATED] = scooter['updated']
            self._attributes[ATTR_ATTRIBUTION] = ATTRIBUTION
