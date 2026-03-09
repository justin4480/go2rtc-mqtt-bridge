# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Lightweight single-file Docker container that polls the go2rtc API and publishes stream data to MQTT. This is the original simple version — the actively maintained successor is `go2rtc2mqtt` (which adds HA discovery, YAML config, and proper packaging).

## Project Structure

```
go2rtc-mqtt-bridge/
├── bridge.py             # Single-class implementation (~90 lines)
├── Dockerfile            # Python 3.11 Alpine (~50MB image)
├── docker-compose.yml    # Service orchestration
└── README.md
```

## Common Operations

```bash
docker-compose up -d
docker-compose logs -f
```

## Configuration

All via environment variables in docker-compose.yml:
- `GO2RTC_API_URL` — go2rtc API endpoint
- `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS`
- `MQTT_TOPIC` — base topic prefix (default: `go2rtc/streams`)
- `POLL_INTERVAL` — seconds between polls (default: 30)
