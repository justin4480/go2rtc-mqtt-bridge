# go2rtc MQTT Bridge

Lightweight Docker container that polls the go2rtc API and publishes tablet consumer data to MQTT with Home Assistant auto-discovery.

## Features

- **Tablet-centric view**: Groups consumers by tablet IP address
- **Home Assistant integration**: Auto-discovery creates devices and sensors
- **Minimal code**: Single Python class, ~150 lines
- **Real-time metrics**: Bandwidth (Mbps) calculated per camera stream
- **Simple**: Direct mapping of go2rtc data, no complex abstractions
- Alpine-based Docker image (~50MB)

## What You Get in Home Assistant

**9 Tablet Devices** (one per Android tablet), each containing:

- **User Agent** - Browser/device info
- **Per-camera metrics** (3 cameras: driveway, garden, street):
  - `{camera}_tablet Source` - ffmpeg source command
  - `{camera}_tablet Format Name` - Stream format (e.g., `mse/fmp4`)
  - `{camera}_tablet Bytes Send` - Total bytes sent
  - `{camera}_tablet Mbps` - Current bandwidth usage

**Example:**
```
Device: Tablet 192.168.50.67
├─ User Agent: "Mozilla/5.0 (Linux; Android 15; SM-X110..."
├─ driveway_tablet Source: "exec:/usr/lib/ffmpeg/7.0/bin/ffmpeg..."
├─ driveway_tablet Format Name: "mse/fmp4"
├─ driveway_tablet Bytes Send: "12495074958"
├─ driveway_tablet Mbps: "2.34"
├─ garden_tablet Source: "exec:/usr/lib/..."
├─ garden_tablet Format Name: "mse/fmp4"
├─ garden_tablet Bytes Send: "12875473399"
├─ garden_tablet Mbps: "1.98"
...
```

## Quick Start

1. **Edit docker-compose.yml** with your settings:
   ```yaml
   - GO2RTC_API_URL=http://192.168.50.8:1984/api/streams
   - MQTT_BROKER=192.168.50.x
   - MQTT_USER=your_user       # Optional
   - MQTT_PASS=your_pass       # Optional
   ```

2. **Build and run**:
   ```bash
   docker-compose up -d
   ```

3. **Check Home Assistant**:
   - Navigate to Settings → Devices & Services → MQTT
   - You should see 9 "Tablet X.X.X.X" devices auto-discovered

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GO2RTC_API_URL` | `http://192.168.50.8:1984/api/streams` | go2rtc API endpoint |
| `MQTT_BROKER` | `localhost` | MQTT broker hostname/IP |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_TOPIC` | `go2rtc/tablets` | MQTT base topic prefix |
| `MQTT_USER` | _(empty)_ | MQTT username (optional) |
| `MQTT_PASS` | _(empty)_ | MQTT password (optional) |
| `POLL_INTERVAL` | `30` | Seconds between API polls |
| `HA_DISCOVERY_PREFIX` | `homeassistant` | HA MQTT discovery prefix |

## MQTT Topic Structure

Tablet-centric topics organized by IP address:

```
go2rtc/tablets/tablet_192_168_50_67/user_agent
go2rtc/tablets/tablet_192_168_50_67/driveway_tablet/source
go2rtc/tablets/tablet_192_168_50_67/driveway_tablet/format_name
go2rtc/tablets/tablet_192_168_50_67/driveway_tablet/bytes_send
go2rtc/tablets/tablet_192_168_50_67/driveway_tablet/mbps
go2rtc/tablets/tablet_192_168_50_67/garden_tablet/source
...
```

## How It Works

1. Polls go2rtc `/api/streams` endpoint every 30 seconds
2. Filters for `*_tablet` streams (consumers are the tablets)
3. Groups consumers by IP address (extracted from `remote_addr`)
4. Publishes MQTT discovery configs for Home Assistant
5. Calculates bandwidth: `(current_bytes - previous_bytes) * 8 / poll_interval / 1,000,000`

## Docker Run (Alternative)

```bash
docker build -t go2rtc-mqtt-bridge .

docker run -d \
  --name go2rtc-mqtt-bridge \
  --restart unless-stopped \
  -e GO2RTC_API_URL=http://192.168.50.8:1984/api/streams \
  -e MQTT_BROKER=192.168.50.x \
  -e MQTT_USER=mqtt-user \
  -e MQTT_PASS=password \
  go2rtc-mqtt-bridge
```

## Troubleshooting

**No devices showing in HA:**
- Check MQTT broker connection: `docker-compose logs -f`
- Verify HA MQTT integration is configured
- Ensure `HA_DISCOVERY_PREFIX` matches HA config (default: `homeassistant`)

**Tablets not detected:**
- Verify go2rtc has streams named `*_tablet` (e.g., `driveway_tablet`)
- Check consumers have `remote_addr` field: `curl http://192.168.50.8:1984/api/streams | jq`

**Mbps showing 0:**
- Normal on first poll (no previous data)
- Will update on next poll (default 30s)

**Missing cameras:**
- Bridge only processes `*_tablet` streams
- Ensure your go2rtc config has `driveway_tablet`, `garden_tablet`, `street_tablet` streams

## MQTT Examples

### Subscribe to all tablet data
```bash
mosquitto_sub -h 192.168.50.x -u mqtt-user -P password -t 'go2rtc/tablets/#' -v
```

### Monitor specific tablet
```bash
mosquitto_sub -h 192.168.50.x -u mqtt-user -P password -t 'go2rtc/tablets/tablet_192_168_50_67/#'
```

### Watch bandwidth metrics
```bash
mosquitto_sub -h 192.168.50.x -u mqtt-user -P password -t 'go2rtc/tablets/+/+/mbps'
```

## Development

The bridge is intentionally minimal (~150 lines) to keep it simple and maintainable:

- **No dataclasses or type hints** - Pure Python dicts
- **Single file** - Everything in `bridge.py`
- **Direct go2rtc mapping** - No abstraction layers
- **Tablet-centric** - Inverts go2rtc's stream-centric model for easier HA visualization

To modify what data is published, edit the `extract_tablets()` and `publish_tablet()` functions.
