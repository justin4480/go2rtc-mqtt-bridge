#!/usr/bin/env python3
import os
import time
import json
import logging
from urllib.request import urlopen
import paho.mqtt.client as mqtt


class Go2RtcClient:
    """Fetches data from go2rtc API."""

    def __init__(self, api_url):
        self.api_url = api_url
        self.logger = logging.getLogger(__name__)

    def fetch_streams(self):
        """Fetch stream data from go2rtc API."""
        try:
            with urlopen(self.api_url, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            self.logger.error(f"API fetch failed: {e}")
            return {}


class TabletExtractor:
    """Extracts tablet data from go2rtc streams."""

    @staticmethod
    def extract_ip(remote_addr):
        """Extract IP from remote_addr (e.g., '192.168.50.67:1234' -> '192.168.50.67')."""
        return remote_addr.split(':')[0] if remote_addr else None

    @staticmethod
    def extract_tablets(streams):
        """Group consumers by tablet IP across all *_tablet streams."""
        tablets = {}

        for stream_name, stream_data in streams.items():
            if not stream_name.endswith('_tablet'):
                continue

            producer = stream_data.get('producers', [{}])[0]

            for consumer in stream_data.get('consumers', []):
                ip = TabletExtractor.extract_ip(consumer.get('remote_addr', ''))
                if not ip:
                    continue

                if ip not in tablets:
                    tablets[ip] = {'user_agent': consumer.get('user_agent', ''), 'streams': {}}

                tablets[ip]['streams'][stream_name] = {
                    'source': producer.get('source', producer.get('url', '')),
                    'format_name': consumer.get('format_name', ''),
                    'bytes_send': consumer.get('bytes_send', 0)
                }

        return tablets


class MbpsCalculator:
    """Calculates bandwidth (Mbps) from bytes sent."""

    def __init__(self, poll_interval):
        self.poll_interval = poll_interval
        self.previous_bytes = {}

    def calculate(self, key, current_bytes):
        """Calculate Mbps for given key. Returns 0 on first call."""
        if key not in self.previous_bytes:
            self.previous_bytes[key] = current_bytes
            return 0

        bytes_diff = current_bytes - self.previous_bytes[key]
        self.previous_bytes[key] = current_bytes
        return round((bytes_diff * 8) / (self.poll_interval * 1_000_000), 2)


class MqttPublisher:
    """Handles MQTT publishing."""

    def __init__(self, broker, port, username='', password=''):
        self.client = mqtt.Client()
        if username:
            self.client.username_pw_set(username, password)
        self.client.on_connect = lambda c, u, f, rc: logging.info(f"MQTT connected: {rc}")
        self.client.connect(broker, port)
        self.client.loop_start()

    def publish(self, topic, payload):
        """Publish message to MQTT topic."""
        logging.info(f"Publishing to topic: {topic}")
        self.client.publish(topic, payload, qos=1, retain=True)


class HADiscoveryPublisher:
    """Publishes Home Assistant MQTT discovery configs."""

    def __init__(self, mqtt_publisher, ha_prefix, mqtt_topic):
        self.mqtt = mqtt_publisher
        self.ha_prefix = ha_prefix
        self.mqtt_topic = mqtt_topic
        self.published = set()

    def publish_sensor(self, device_id, entity_id, name, state_topic, device, unit=None):
        """Publish single sensor discovery config."""
        unique_key = f"{device_id}_{entity_id}"
        if unique_key in self.published:
            return

        config = {
            'name': name,
            'unique_id': f"go2rtc_{device_id}_{entity_id}",
            'state_topic': state_topic,
            'device': device
        }
        if unit:
            config['unit_of_measurement'] = unit

        topic = f"{self.ha_prefix}/sensor/go2rtc_{device_id}/{entity_id}/config"
        self.mqtt.publish(topic, json.dumps(config))
        self.published.add(unique_key)

    def create_device_config(self, ip):
        """Create HA device config for a tablet."""
        device_id = f"tablet_{ip.replace('.', '_')}"
        return {
            'identifiers': [f"go2rtc_{device_id}"],
            'name': f"Tablet {ip}",
            'manufacturer': 'go2rtc',
            'model': 'Android Tablet'
        }


class TabletPublisher:
    """Publishes tablet data to MQTT."""

    def __init__(self, mqtt_publisher, ha_publisher, mqtt_topic, mbps_calc):
        self.mqtt = mqtt_publisher
        self.ha = ha_publisher
        self.mqtt_topic = mqtt_topic
        self.mbps_calc = mbps_calc

    def publish(self, ip, tablet_data):
        """Publish all data for one tablet."""
        device_id = f"tablet_{ip.replace('.', '_')}"
        base_topic = f"{self.mqtt_topic}/{device_id}"
        device = self.ha.create_device_config(ip)

        self._publish_user_agent(device_id, base_topic, device, tablet_data['user_agent'])
        self._publish_streams(ip, device_id, base_topic, device, tablet_data['streams'])

    def _publish_user_agent(self, device_id, base_topic, device, user_agent):
        """Publish user agent sensor."""
        self.ha.publish_sensor(device_id, 'user_agent', 'User Agent',
                               f"{base_topic}/user_agent", device)
        self.mqtt.publish(f"{base_topic}/user_agent", user_agent)

    def _publish_streams(self, ip, device_id, base_topic, device, streams):
        """Publish all stream sensors for a tablet."""
        for stream_name, stream_info in streams.items():
            self._publish_stream(ip, device_id, base_topic, device, stream_name, stream_info)

    def _publish_stream(self, ip, device_id, base_topic, device, stream_name, stream_info):
        """Publish sensors for a single stream."""
        for field in ['source', 'format_name', 'bytes_send']:
            self._publish_field(device_id, base_topic, device, stream_name, field, stream_info[field])

        self._publish_mbps(ip, device_id, base_topic, device, stream_name, stream_info['bytes_send'])

    def _publish_field(self, device_id, base_topic, device, stream_name, field, value):
        """Publish a single field sensor."""
        entity_id = f"{stream_name}_{field}"
        name = f"{stream_name} {field.replace('_', ' ').title()}"
        state_topic = f"{base_topic}/{stream_name}/{field}"

        self.ha.publish_sensor(device_id, entity_id, name, state_topic, device)
        self.mqtt.publish(state_topic, str(value))

    def _publish_mbps(self, ip, device_id, base_topic, device, stream_name, bytes_send):
        """Publish Mbps sensor."""
        entity_id = f"{stream_name}_mbps"
        state_topic = f"{base_topic}/{stream_name}/mbps"

        mbps = self.mbps_calc.calculate(f"{ip}_{stream_name}", bytes_send)

        self.ha.publish_sensor(device_id, entity_id, f"{stream_name} Mbps",
                               state_topic, device, unit='Mbps')
        self.mqtt.publish(state_topic, str(mbps))


class Bridge:
    """Main bridge orchestrator."""

    def __init__(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

        poll_interval = int(os.getenv('POLL_INTERVAL', '30'))

        self.client = Go2RtcClient(os.getenv('GO2RTC_API_URL', 'http://192.168.50.8:1984/api/streams'))
        self.extractor = TabletExtractor()
        self.mbps_calc = MbpsCalculator(poll_interval)

        mqtt_pub = MqttPublisher(
            os.getenv('MQTT_BROKER', 'localhost'),
            int(os.getenv('MQTT_PORT', '1883')),
            os.getenv('MQTT_USER', ''),
            os.getenv('MQTT_PASS', '')
        )

        ha_pub = HADiscoveryPublisher(
            mqtt_pub,
            os.getenv('HA_DISCOVERY_PREFIX', 'homeassistant'),
            os.getenv('MQTT_TOPIC', 'go2rtc/tablets')
        )

        self.publisher = TabletPublisher(mqtt_pub, ha_pub,
                                         os.getenv('MQTT_TOPIC', 'go2rtc/tablets'),
                                         self.mbps_calc)
        self.poll_interval = poll_interval

    def run(self):
        """Main loop."""
        time.sleep(1)  # Wait for MQTT connection
        self.logger.info(f"Bridge started, polling every {self.poll_interval}s")

        while True:
            streams = self.client.fetch_streams()
            tablets = self.extractor.extract_tablets(streams)

            for ip, tablet_data in tablets.items():
                self.publisher.publish(ip, tablet_data)

            if tablets:
                self.logger.info(f"Published {len(tablets)} tablets")

            time.sleep(self.poll_interval)


if __name__ == '__main__':
    Bridge().run()
