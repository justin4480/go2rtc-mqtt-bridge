#!/usr/bin/env python3
import os
import time
import json
import logging
from urllib.request import urlopen
import paho.mqtt.client as mqtt


class Go2RtcMqttBridge:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

        # Config
        self.api_url = os.getenv('GO2RTC_API_URL', 'http://192.168.50.8:1984/api/streams')
        self.mqtt_topic = os.getenv('MQTT_TOPIC', 'go2rtc/tablets')
        self.ha_prefix = os.getenv('HA_DISCOVERY_PREFIX', 'homeassistant')
        self.poll_interval = int(os.getenv('POLL_INTERVAL', '30'))

        # MQTT
        self.client = mqtt.Client()
        if os.getenv('MQTT_USER'):
            self.client.username_pw_set(os.getenv('MQTT_USER'), os.getenv('MQTT_PASS', ''))
        self.client.on_connect = lambda c, u, f, rc: self.logger.info(f"MQTT connected: {rc}")
        self.published = set()
        self.previous_bytes = {}  # Track previous bytes_send for mbps calculation

    def fetch_data(self):
        """Fetch go2rtc API data."""
        try:
            with urlopen(self.api_url, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            self.logger.error(f"API fetch failed: {e}")
            return {}

    def extract_tablets(self, data):
        """Group consumers by tablet IP across all *_tablet streams."""
        tablets = {}

        for stream_name, stream_data in data.items():
            if not stream_name.endswith('_tablet'):
                continue

            producer = stream_data.get('producers', [{}])[0]

            for consumer in stream_data.get('consumers', []):
                ip = consumer.get('remote_addr', '').split(':')[0]
                if not ip:
                    continue

                if ip not in tablets:
                    tablets[ip] = {
                        'user_agent': consumer.get('user_agent', ''),
                        'streams': {}
                    }

                tablets[ip]['streams'][stream_name] = {
                    'source': producer.get('source', producer.get('url', '')),
                    'format_name': consumer.get('format_name', ''),
                    'bytes_send': consumer.get('bytes_send', 0)
                }

        return tablets

    def publish(self, topic, payload, retain=True):
        """Publish to MQTT."""
        self.client.publish(topic, payload, qos=1, retain=retain)

    def publish_tablet(self, ip, tablet_data):
        """Publish HA discovery and state for one tablet."""
        device_id = f"tablet_{ip.replace('.', '_')}"
        base = f"{self.mqtt_topic}/{device_id}"

        # Shared device config (must be identical across all sensors)
        device = {
            'identifiers': [f"go2rtc_{device_id}"],
            'name': f"Tablet {ip}",
            'manufacturer': 'go2rtc',
            'model': 'Android Tablet'
        }

        # User agent sensor
        key = f"sensor_{device_id}_user_agent"
        if key not in self.published:
            config = {
                'name': 'User Agent',
                'unique_id': f"go2rtc_{device_id}_user_agent",
                'state_topic': f"{base}/user_agent",
                'icon': 'mdi:tablet',
                'device': device
            }
            self.publish(f"{self.ha_prefix}/sensor/go2rtc_{device_id}/user_agent/config", json.dumps(config))
            self.published.add(key)

        self.publish(f"{base}/user_agent", tablet_data['user_agent'])

        # Stream sensors (source, format, bytes, mbps per camera)
        for stream_name, stream_info in tablet_data['streams'].items():
            # Publish basic fields
            for field in ['source', 'format_name', 'bytes_send']:
                key = f"sensor_{device_id}_{stream_name}_{field}"
                if key not in self.published:
                    config = {
                        'name': f"{stream_name} {field.replace('_', ' ').title()}",
                        'unique_id': f"go2rtc_{device_id}_{stream_name}_{field}",
                        'state_topic': f"{base}/{stream_name}/{field}",
                        'device': device
                    }
                    self.publish(f"{self.ha_prefix}/sensor/go2rtc_{device_id}/{stream_name}_{field}/config", json.dumps(config))
                    self.published.add(key)

                self.publish(f"{base}/{stream_name}/{field}", str(stream_info[field]))

            # Calculate and publish mbps
            bytes_key = f"{ip}_{stream_name}"
            current_bytes = stream_info['bytes_send']
            mbps = 0

            if bytes_key in self.previous_bytes:
                bytes_diff = current_bytes - self.previous_bytes[bytes_key]
                mbps = round((bytes_diff * 8) / (self.poll_interval * 1_000_000), 2)  # Convert to Mbps

            self.previous_bytes[bytes_key] = current_bytes

            key = f"sensor_{device_id}_{stream_name}_mbps"
            if key not in self.published:
                config = {
                    'name': f"{stream_name} Mbps",
                    'unique_id': f"go2rtc_{device_id}_{stream_name}_mbps",
                    'state_topic': f"{base}/{stream_name}/mbps",
                    'unit_of_measurement': 'Mbps',
                    'device': device
                }
                self.publish(f"{self.ha_prefix}/sensor/go2rtc_{device_id}/{stream_name}_mbps/config", json.dumps(config))
                self.published.add(key)

            self.publish(f"{base}/{stream_name}/mbps", str(mbps))

    def run(self):
        """Main loop."""
        self.client.connect(os.getenv('MQTT_BROKER', 'localhost'), int(os.getenv('MQTT_PORT', '1883')))
        self.client.loop_start()
        time.sleep(1)

        self.logger.info(f"Bridge started, polling every {self.poll_interval}s")

        while True:
            data = self.fetch_data()
            tablets = self.extract_tablets(data)

            for ip, tablet_data in tablets.items():
                self.publish_tablet(ip, tablet_data)

            if tablets:
                self.logger.info(f"Published {len(tablets)} tablets")

            time.sleep(self.poll_interval)


if __name__ == '__main__':
    Go2RtcMqttBridge().run()
