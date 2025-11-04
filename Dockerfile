FROM python:3.11-alpine

WORKDIR /app

RUN pip install --no-cache-dir paho-mqtt

COPY bridge.py .

RUN chmod +x bridge.py

CMD ["python", "-u", "bridge.py"]
