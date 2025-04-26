FROM python:3.12-slim

RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

WORKDIR /app

COPY main.py .

RUN pip install gpxpy geopy tqdm

ENTRYPOINT ["python", "add_speed_overlay.py"]
