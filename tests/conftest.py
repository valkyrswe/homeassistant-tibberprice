"""Shared fixtures for tibberprice tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock


def make_price(starts_at, total, energy=0.5, tax=0.1):
    return {"startsAt": starts_at, "total": total, "energy": energy, "tax": tax}


SAMPLE_TODAY = [
    make_price("2026-03-12T00:00:00+01:00", 1.0),
    make_price("2026-03-12T01:00:00+01:00", 0.8),
    make_price("2026-03-12T02:00:00+01:00", 0.6),
    make_price("2026-03-12T14:00:00+01:00", 1.5),
    make_price("2026-03-12T23:00:00+01:00", 2.0),
]

SAMPLE_TOMORROW = [
    make_price("2026-03-13T00:00:00+01:00", 1.1),
    make_price("2026-03-13T12:00:00+01:00", 0.9),
]

SAMPLE_API_RESPONSE = {
    "data": {
        "viewer": {
            "homes": [
                {
                    "currentSubscription": {
                        "priceInfo": {
                            "today": SAMPLE_TODAY,
                            "tomorrow": SAMPLE_TOMORROW,
                        }
                    }
                }
            ]
        }
    }
}

SAMPLE_API_RESPONSE_NO_TOMORROW = {
    "data": {
        "viewer": {
            "homes": [
                {
                    "currentSubscription": {
                        "priceInfo": {
                            "today": SAMPLE_TODAY,
                            "tomorrow": [],
                        }
                    }
                }
            ]
        }
    }
}

SAMPLE_API_RESPONSE_NO_TODAY = {
    "data": {
        "viewer": {
            "homes": [
                {
                    "currentSubscription": {
                        "priceInfo": {
                            "tomorrow": SAMPLE_TOMORROW,
                        }
                    }
                }
            ]
        }
    }
}


@pytest.fixture
def mock_hass():
    hass = MagicMock()

    async def executor_job(func):
        return func()

    hass.async_add_executor_job = AsyncMock(side_effect=executor_job)
    return hass
