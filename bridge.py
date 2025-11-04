#!/usr/bin/env python3
import os
import time
import json
import logging
from urllib.request import urlopen
from urllib.error import URLError
import paho.mqtt.client as mqtt


class Go2RtcMqttBridge:
    def __init__(self):
        self.api_url = os.getenv('GO2RTC_API_URL', 'http://192.168.50.8:1984/api/streams')
        self.mqtt_broker = os.getenv('MQTT_BROKER', 'localhost')
        self.mqtt_port = int(os.getenv('MQTT_PORT', '1883'))
        self.mqtt_topic = os.getenv('MQTT_TOPIC', 'go2rtc/streams')
        self.mqtt_user = os.getenv('MQTT_USER', '')
        self.mqtt_pass = os.getenv('MQTT_PASS', '')
        self.poll_interval = int(os.getenv('POLL_INTERVAL', '30'))

        self.client = mqtt.Client()
        if self.mqtt_user and self.mqtt_pass:
            self.client.username_pw_set(self.mqtt_user, self.mqtt_pass)

        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

    def connect_mqtt(self):
        try:
            self.client.connect(self.mqtt_broker, self.mqtt_port)
            self.client.loop_start()
            self.logger.info(f"Connected to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}")
        except Exception as e:
            self.logger.error(f"Failed to connect to MQTT broker: {e}")
            raise

    def fetch_api_data(self):
        try:
            with urlopen(self.api_url, timeout=10) as response:
                return json.loads(response.read())
        except URLError as e:
            self.logger.error(f"Failed to fetch API data: {e}")
            return None

    def publish_to_mqtt(self, data):
        if not isinstance(data, dict):
            self.logger.error("API data is not a dictionary")
            return

        published_count = 0
        try:
            for stream_name, stream_data in data.items():
                base_topic = f"{self.mqtt_topic}/{stream_name}"

                # Publish producers
                if 'producers' in stream_data and isinstance(stream_data['producers'], list):
                    for idx, producer in enumerate(stream_data['producers']):
                        topic = f"{base_topic}/producers/{idx}"
                        self.client.publish(topic, json.dumps(producer), qos=1, retain=True)
                        published_count += 1

                # Publish consumers
                if 'consumers' in stream_data and isinstance(stream_data['consumers'], list):
                    for idx, consumer in enumerate(stream_data['consumers']):
                        # Extract URL for better topic naming if available
                        url = consumer.get('url', '')
                        topic_suffix = url.replace('://', '_').replace('/', '_').replace(':', '_') if url else str(idx)
                        topic = f"{base_topic}/consumers/{topic_suffix}"
                        self.client.publish(topic, json.dumps(consumer), qos=1, retain=True)
                        published_count += 1

            if published_count > 0:
                self.logger.info(f"Published {published_count} topics")
        except Exception as e:
            self.logger.error(f"Error publishing to MQTT: {e}")

    def run(self):
        self.connect_mqtt()
        self.logger.info(f"Starting bridge - polling every {self.poll_interval}s")

        while True:
            data = self.fetch_api_data()
            if data is not None:
                self.publish_to_mqtt(data)
            time.sleep(self.poll_interval)


if __name__ == '__main__':
    bridge = Go2RtcMqttBridge()
    bridge.run()
