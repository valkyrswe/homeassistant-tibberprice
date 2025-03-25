#Imports
import logging
import requests
import voluptuous as vol

from datetime import datetime
from dateutil.parser import isoparse
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_URL, CONF_NAME
from homeassistant.helpers.event import async_track_time_change
import homeassistant.helpers.config_validation as cv

#
_LOGGER = logging.getLogger(__name__)

CONF_TOKEN = "token"
DEFAULT_NAME = "Tibber Price"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_URL): cv.string,
    vol.Optional(CONF_TOKEN): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string
})

#Setup initial async
async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    url = config[CONF_URL]
    token = config.get(CONF_TOKEN)
    name = config.get(CONF_NAME)

    coordinator = TibberPriceDataCoordinator(hass, url, token)
    sensors = [
        TibberPriceSensor(f"{name} Current Price", coordinator, "current"),
        TibberPriceSensor(f"{name} Cheapest Hour", coordinator, "cheapest"),
        TibberPriceSensor(f"{name} Most Expensive Hour", coordinator, "most_expensive"),
        TibberPriceSensor(f"{name} Next Hour", coordinator, "next"),
        TibberPriceSensor(f"{name} Average Price Tomorrow", coordinator, "tomorrow_avg")
    ]

    coordinator.set_sensors(sensors)
# Set the sensor to only update when new prices are available (usually between 16:00–18:00),
# but we now check every hour to catch updates reliably.
async def scheduled_refresh(now):
    _LOGGER.info("Scheduled Tibber update at %s", now.strftime("%H:%M"))
    await coordinator.async_update()

# Schedule an update every hour on the hour
for hour in range(0, 24, 1):
    async_track_time_change(
        hass,
        scheduled_refresh,
        hour=hour,
        minute=0,
        second=0
    )

async_add_entities(sensors)

# Define variables for API call. 
class TibberPriceDataCoordinator:
    def __init__(self, hass, url, token):
        self.hass = hass
        self.url = url
        self.token = token
        self.prices = []
        self.cheapest = None
        self.most_expensive = None
        self.next_hour = None
        self.tomorrow_avg = None
        self.sensors = []

    def set_sensors(self, sensors):
        self.sensors = sensors
        # Define the acual API call, took it from Tibbers developer portal.
    async def async_update(self):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        query = """
        {
          viewer {
            homes {
              currentSubscription {
                priceInfo {
                  today {
                    total
                    energy
                    tax
                    startsAt
                  }
                  tomorrow {
                    total
                    energy
                    tax
                    startsAt
                  }
                }
              }
            }
          }
        }
        """

        try:
            response = await self.hass.async_add_executor_job(
                lambda: requests.post(
                    self.url,
                    headers={**headers, "Content-Type": "application/json"},
                    json={"query": query}
                )
            )
# Check is response is good, portion the parts in the attributes for the sensors. 
            if response.status_code == 200:
                data = response.json()
                prices_today = data["data"]["viewer"]["homes"][0]["currentSubscription"]["priceInfo"]["today"]
                prices_tomorrow = data["data"]["viewer"]["homes"][0]["currentSubscription"]["priceInfo"].get("tomorrow", [])

                self.prices = prices_today + prices_tomorrow

                now = datetime.now().isoformat()
                upcoming = [p for p in self.prices if p["startsAt"] > now]

                if self.prices:
                    self.cheapest = min(self.prices, key=lambda x: x["total"])
                    self.most_expensive = max(self.prices, key=lambda x: x["total"])

                if upcoming:
                    self.next_hour = upcoming[0]

                if prices_tomorrow:
                    self.tomorrow_avg = sum(p["total"] for p in prices_tomorrow) / len(prices_tomorrow)

                for sensor in self.sensors:
                    if getattr(sensor, "_ready", False):
                        sensor.async_schedule_update_ha_state()

            else:
                _LOGGER.error("TibberPrice HTTP %s: %s", response.status_code, response.text)

        except Exception as e:
            _LOGGER.exception("Error fetching Tibber data: %s", e)


class TibberPriceSensor(SensorEntity):
    def __init__(self, name, coordinator, sensor_type):
        self._attr_name = name
        self.coordinator = coordinator
        self.sensor_type = sensor_type
        self._state = None
        self._attributes = {}
        self._ready = False  # Will be set true after added to HA

    async def async_added_to_hass(self):
        """Mark the sensor as ready and trigger update once it's safe."""
        self._ready = True
        await self.coordinator.async_update()

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    def update(self):
        def format_attributes(data):
            if not data:
                return {}
            dt = isoparse(data["startsAt"])
            return {
                **data,
                "date": dt.date().isoformat(),
                "time": dt.time().isoformat(timespec="minutes")
            }

        if self.sensor_type == "current":
            now = datetime.now().replace(minute=0, second=0, microsecond=0).isoformat()
            match = next((p for p in self.coordinator.prices if p["startsAt"].startswith(now)), None)
            if match:
                self._state = match["total"]
                self._attributes = format_attributes(match)

        elif self.sensor_type == "cheapest":
            if self.coordinator.cheapest:
                self._state = self.coordinator.cheapest["total"]
                self._attributes = format_attributes(self.coordinator.cheapest)

        elif self.sensor_type == "most_expensive":
            if self.coordinator.most_expensive:
                self._state = self.coordinator.most_expensive["total"]
                self._attributes = format_attributes(self.coordinator.most_expensive)

        elif self.sensor_type == "next":
            if self.coordinator.next_hour:
                self._state = self.coordinator.next_hour["total"]
                self._attributes = format_attributes(self.coordinator.next_hour)

        elif self.sensor_type == "tomorrow_avg":
            if self.coordinator.tomorrow_avg is not None:
                self._state = round(self.coordinator.tomorrow_avg, 3)
                self._attributes = {"label": "average price for tomorrow"}
