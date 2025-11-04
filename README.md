# go2rtc2mqtt Bridge

Lightweight Docker container that polls the go2rtc API and publishes stream data to MQTT.

## Features

- Minimal Python implementation (single class, ~90 lines)
- Structured MQTT topics per stream/producer/consumer
- Alpine-based Docker image (~50MB)
- Configurable polling interval
- Optional MQTT authentication
- Auto-reconnect handling
- Retained messages for last known state

## Quick Start

1. **Edit docker-compose.yml** with your settings:
   ```yaml
   - MQTT_BROKER=192.168.50.x  # Your MQTT broker IP
   - MQTT_USER=your_user       # Optional
   - MQTT_PASS=your_pass       # Optional
   ```

2. **Build and run**:
   ```bash
   docker-compose up -d
   ```

3. **Check logs**:
   ```bash
   docker-compose logs -f
   ```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GO2RTC_API_URL` | `http://192.168.50.8:1984/api/streams` | go2rtc API endpoint |
| `MQTT_BROKER` | `localhost` | MQTT broker hostname/IP |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_TOPIC` | `go2rtc/streams` | MQTT base topic prefix |
| `MQTT_USER` | _(empty)_ | MQTT username (optional) |
| `MQTT_PASS` | _(empty)_ | MQTT password (optional) |
| `POLL_INTERVAL` | `30` | Seconds between API polls |

## MQTT Topic Structure

Each stream's producers and consumers are published as separate MQTT topics:

```
go2rtc/streams/{stream_name}/producers/{index}
go2rtc/streams/{stream_name}/consumers/{url_or_index}
```

### Example Topics

For a stream named `driveway_tablets`:

```
go2rtc/streams/driveway_tablets/producers/0
go2rtc/streams/driveway_tablets/consumers/tcp_192.168.50.57_8554

Payload:
{
  "url": "tcp://192.168.50.57:8554",
  "format_name": "mse/fmp4",
  "bytes": 34268724,
  "send_bytes": 172364,
  ...
}
```

### Benefits

- Subscribe to specific streams: `go2rtc/streams/driveway_tablets/#`
- Monitor all consumers: `go2rtc/streams/+/consumers/#`
- Track individual producer/consumer stats
- Easier integration with Home Assistant, Node-RED, etc.

## Docker Run (Alternative)

```bash
docker build -t go2rtc2mqtt .

docker run -d \
  --name go2rtc2mqtt \
  --restart unless-stopped \
  -e MQTT_BROKER=192.168.50.x \
  go2rtc2mqtt
```

## Proxmox Deployment

1. Copy files to your Proxmox host or LXC container
2. Install Docker if not already available
3. Run `docker-compose up -d`
4. Monitor with `docker-compose logs -f`

## Troubleshooting

- **Can't reach go2rtc API**: Ensure Docker can reach `192.168.50.8` (use `network_mode: host` if needed)
- **MQTT connection fails**: Check broker IP, port, and credentials
- **High CPU usage**: Increase `POLL_INTERVAL` to poll less frequently

## MQTT Examples

### Subscribe to all topics
```bash
mosquitto_sub -h 192.168.50.x -u mqtt-user -P password -t 'go2rtc/streams/#' -v
```

### Subscribe to specific stream
```bash
mosquitto_sub -h 192.168.50.x -u mqtt-user -P password -t 'go2rtc/streams/driveway_tablets/#'
```

### Monitor only consumers
```bash
mosquitto_sub -h 192.168.50.x -u mqtt-user -P password -t 'go2rtc/streams/+/consumers/#'
```
