# homeassistant-tibberprice

A Home Assistant custom component that pulls current and future electricity prices from the [Tibber API](https://developer.tibber.com/) and exposes them as sensors.

## Installation

1. Copy the contents of this repository into your Home Assistant `custom_components/tibberprice/` directory:
   ```
   <config>/custom_components/tibberprice/sensor.py
   <config>/custom_components/tibberprice/manifest.json
   ```
2. Restart Home Assistant.

## Configuration

Add the following to your `configuration.yaml`:

```yaml
sensor:
  - platform: tibberprice
    url: "https://api.tibber.com/v1-beta/gql"
    token: YOUR_TIBBER_API_TOKEN
    name: "Tibber Price"   # optional, default: "Tibber Price"
    unit: "NOK/kWh"        # optional, default: "NOK/kWh"
```

### Getting a Tibber API token

1. Log in at [developer.tibber.com](https://developer.tibber.com/)
2. Go to **API** and generate a Personal Access Token.

## Sensors

Five sensors are created, all prefixed with the configured `name`:

| Sensor | Description |
|--------|-------------|
| `{name} Current Price` | Price for the current hour. Attributes include the full price list (used by template sensors). |
| `{name} Cheapest Hour` | Cheapest hour across today and tomorrow. |
| `{name} Most Expensive Hour` | Most expensive hour across today and tomorrow. |
| `{name} Next Hour` | Price for the next upcoming hour. |
| `{name} Average Price Tomorrow` | Average price across tomorrow's hours (available after ~13:00–15:00 CET). |

## Template Sensors

The repository includes optional Jinja2 template sensors that calculate how many minutes remain until the cheapest upcoming hour within a given window:

| File | Window |
|------|--------|
| `template_3hour.yaml` | 3 hours |
| `template_6hour.yaml` | 6 hours |
| `template_12hour.yaml` | 12 hours |
| `templates_tibber.yaml` | 24 hours |

To use them, paste the contents into your `configuration.yaml` under a `template:` block, or include them via `!include`.

## Running Tests

```bash
pip install -r requirements_test.txt
pytest tests/
```
