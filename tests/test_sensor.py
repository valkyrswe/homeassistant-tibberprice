"""Tests for the tibberprice sensor integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import timezone, timedelta

from tests.conftest import (
    SAMPLE_TODAY,
    SAMPLE_TOMORROW,
    SAMPLE_API_RESPONSE,
    SAMPLE_API_RESPONSE_NO_TOMORROW,
    SAMPLE_API_RESPONSE_NO_TODAY,
    make_price,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_coordinator(mock_hass, url="https://api.tibber.com/v1-beta/gql", token="tok"):
    from sensor import TibberPriceDataCoordinator
    return TibberPriceDataCoordinator(mock_hass, url, token)


def make_sensor(coordinator, sensor_type="current", unit="NOK/kWh"):
    from sensor import TibberPriceSensor
    return TibberPriceSensor(f"Tibber {sensor_type}", coordinator, sensor_type, unit)


def mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


# ---------------------------------------------------------------------------
# a) async_setup_platform loads without error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_setup_platform_no_error(mock_hass):
    """Regression for scoping bug 1.1 — platform must load without NameError."""
    import sensor as sensor_module

    added_entities = []

    async def fake_async_add_entities(entities):
        added_entities.extend(entities)

    config = {
        "platform": "tibberprice",
        "url": "https://api.tibber.com/v1-beta/gql",
        "token": "test-token",
        "name": "Tibber Price",
        "unit": "NOK/kWh",
    }

    with patch("sensor.async_track_time_change") as mock_track:
        await sensor_module.async_setup_platform(
            mock_hass, config, fake_async_add_entities
        )

    assert len(added_entities) == 5
    sensor_types = [s.sensor_type for s in added_entities]
    assert sensor_types == ["current", "cheapest", "most_expensive", "next", "tomorrow_avg"]


# ---------------------------------------------------------------------------
# b) async_update with valid 200 response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_update_success(mock_hass):
    """Coordinator extracts prices, cheapest, most_expensive, next_hour, tomorrow_avg."""
    coordinator = make_coordinator(mock_hass)

    with patch("requests.post", return_value=mock_response(SAMPLE_API_RESPONSE)):
        await coordinator.async_update()

    all_prices = SAMPLE_TODAY + SAMPLE_TOMORROW
    assert coordinator.prices == all_prices
    assert coordinator.cheapest["total"] == min(p["total"] for p in all_prices)
    assert coordinator.most_expensive["total"] == max(p["total"] for p in all_prices)
    expected_avg = sum(p["total"] for p in SAMPLE_TOMORROW) / len(SAMPLE_TOMORROW)
    assert abs(coordinator.tomorrow_avg - expected_avg) < 1e-9


# ---------------------------------------------------------------------------
# c) async_update with HTTP non-200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_update_http_error(mock_hass):
    """HTTP error is logged; coordinator state is not updated."""
    coordinator = make_coordinator(mock_hass)
    coordinator.prices = []

    with patch("requests.post", return_value=mock_response({}, status_code=401)):
        with patch("sensor._LOGGER") as mock_logger:
            await coordinator.async_update()

    mock_logger.error.assert_called_once()
    assert coordinator.prices == []


# ---------------------------------------------------------------------------
# d) async_update with network exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_update_network_exception(mock_hass):
    """Network exception is caught and logged; does not propagate."""
    import requests as req
    coordinator = make_coordinator(mock_hass)

    with patch("requests.post", side_effect=req.exceptions.ConnectionError("timeout")):
        with patch("sensor._LOGGER") as mock_logger:
            await coordinator.async_update()  # must not raise

    mock_logger.exception.assert_called_once()


# ---------------------------------------------------------------------------
# e) "current" sensor timezone matching
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_current_sensor_timezone_match(mock_hass):
    """Regression for timezone bug 1.3 — current sensor state must not be None."""
    from homeassistant.util import dt as dt_util

    coordinator = make_coordinator(mock_hass)
    now_hour = dt_util.now().replace(minute=0, second=0, microsecond=0)
    # Build a price entry whose startsAt is exactly the current hour in UTC+1
    offset = timedelta(hours=1)
    starts_at = now_hour.astimezone(timezone(offset)).strftime("%Y-%m-%dT%H:%M:%S+01:00")
    current_price = make_price(starts_at, 1.23)
    coordinator.prices = [current_price]

    sensor = make_sensor(coordinator, "current")
    sensor.update()

    assert sensor.state == 1.23


# ---------------------------------------------------------------------------
# f) next_hour resets to None when all prices are in the past
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_next_hour_resets_when_no_upcoming(mock_hass):
    """Regression for bug 1.5 — next_hour should be None at end of day."""
    coordinator = make_coordinator(mock_hass)

    # All prices are far in the past
    past_prices = [make_price("2020-01-01T00:00:00+00:00", 1.0)]
    response_data = {
        "data": {
            "viewer": {
                "homes": [
                    {
                        "currentSubscription": {
                            "priceInfo": {
                                "today": past_prices,
                                "tomorrow": [],
                            }
                        }
                    }
                ]
            }
        }
    }

    coordinator.next_hour = make_price("2020-01-01T00:00:00+00:00", 9.99)  # stale
    with patch("requests.post", return_value=mock_response(response_data)):
        await coordinator.async_update()

    assert coordinator.next_hour is None


# ---------------------------------------------------------------------------
# g) Missing "today" key does not raise
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_today_key_does_not_raise(mock_hass):
    """Regression for bug 1.4 — missing today key must not raise KeyError."""
    coordinator = make_coordinator(mock_hass)

    with patch("requests.post", return_value=mock_response(SAMPLE_API_RESPONSE_NO_TODAY)):
        with patch("sensor._LOGGER"):
            await coordinator.async_update()  # must not raise


# ---------------------------------------------------------------------------
# h) Single time-change listener registered
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_time_change_listener(mock_hass):
    """Regression for bug 1.2 — exactly one async_track_time_change call."""
    import sensor as sensor_module

    config = {
        "platform": "tibberprice",
        "url": "https://api.tibber.com/v1-beta/gql",
        "token": "test-token",
        "name": "Tibber Price",
        "unit": "NOK/kWh",
    }

    with patch("sensor.async_track_time_change") as mock_track:
        await sensor_module.async_setup_platform(
            mock_hass, config, AsyncMock()
        )

    assert mock_track.call_count == 1
    _, kwargs = mock_track.call_args
    assert kwargs.get("hour") is None
    assert kwargs.get("minute") == 0
    assert kwargs.get("second") == 0


# ---------------------------------------------------------------------------
# i) tomorrow_avg is None when no tomorrow prices
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tomorrow_avg_none_when_no_tomorrow(mock_hass):
    """tomorrow_avg should be None when tomorrow prices are empty."""
    coordinator = make_coordinator(mock_hass)
    coordinator.tomorrow_avg = 1.5  # stale value

    with patch("requests.post", return_value=mock_response(SAMPLE_API_RESPONSE_NO_TOMORROW)):
        await coordinator.async_update()

    assert coordinator.tomorrow_avg is None


# ---------------------------------------------------------------------------
# j) All five sensor types — state and attributes
# ---------------------------------------------------------------------------

def test_sensor_types_state_and_attributes(mock_hass):
    """All five sensor types return correct state and attributes."""
    coordinator = make_coordinator(mock_hass)
    coordinator.prices = SAMPLE_TODAY + SAMPLE_TOMORROW
    coordinator.cheapest = min(coordinator.prices, key=lambda x: x["total"])
    coordinator.most_expensive = max(coordinator.prices, key=lambda x: x["total"])
    coordinator.next_hour = coordinator.prices[3]  # arbitrary future-ish entry
    coordinator.tomorrow_avg = sum(p["total"] for p in SAMPLE_TOMORROW) / len(SAMPLE_TOMORROW)

    # cheapest
    s = make_sensor(coordinator, "cheapest")
    s.update()
    assert s.state == coordinator.cheapest["total"]
    assert s.extra_state_attributes["startsAt"] == coordinator.cheapest["startsAt"]
    assert "date" in s.extra_state_attributes
    assert "time" in s.extra_state_attributes

    # most_expensive
    s = make_sensor(coordinator, "most_expensive")
    s.update()
    assert s.state == coordinator.most_expensive["total"]

    # next
    s = make_sensor(coordinator, "next")
    s.update()
    assert s.state == coordinator.next_hour["total"]

    # tomorrow_avg
    s = make_sensor(coordinator, "tomorrow_avg")
    s.update()
    assert s.state == round(coordinator.tomorrow_avg, 3)
    assert s.extra_state_attributes == {"label": "average price for tomorrow"}

    # tomorrow_avg with None — state should not change
    coordinator.tomorrow_avg = None
    s = make_sensor(coordinator, "tomorrow_avg")
    s.update()
    assert s.state is None


def test_format_attributes_with_none(mock_hass):
    """format_attributes returns empty dict for falsy input."""
    # Trigger via cheapest sensor with no data
    coordinator = make_coordinator(mock_hass)
    coordinator.cheapest = None

    s = make_sensor(coordinator, "cheapest")
    s.update()
    assert s.state is None
    assert s.extra_state_attributes == {}


def test_current_sensor_exposes_prices_attribute(mock_hass):
    """'current' sensor attributes include all prices list."""
    from homeassistant.util import dt as dt_util
    from datetime import timezone, timedelta

    coordinator = make_coordinator(mock_hass)
    now_hour = dt_util.now().replace(minute=0, second=0, microsecond=0)
    offset = timedelta(hours=1)
    starts_at = now_hour.astimezone(timezone(offset)).strftime("%Y-%m-%dT%H:%M:%S+01:00")
    current_price = make_price(starts_at, 1.0)
    coordinator.prices = [current_price]

    s = make_sensor(coordinator, "current")
    s.update()

    assert "prices" in s.extra_state_attributes
    assert s.extra_state_attributes["prices"] == coordinator.prices
