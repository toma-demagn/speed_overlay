# Speed Overlay Video Generator

This project allows you to **overlay GPS-based speed information** onto a video file, based on a provided `.gpx` track log.

It automatically:
- Parses your GPX data
- Calculates speed at each video frame
- Creates a dynamic speed overlay (ASS subtitles)
- Merges the overlay into the video using FFmpeg

No frames are loaded into memory individually — it's efficient and streaming-based using ASS subtitles.

This concept can be generalized to efficiently add any text to a video.

---

## 🛠 Requirements

You can run the project:
- **Locally** (with Python and FFmpeg installed)
- **Or** inside a **Docker container** (no installation needed)

---

## 📦 How to Build the Docker Image and Run

If using Docker, first build the image:

```bash
docker build -t speed_overlay .
```

Then run :

```bash
docker run --rm -v "$(pwd)/data:/app/data" speed_overlay data/cycling.mp4 data/activity.gpx --output data/output.mp4 --video_date 2025-03-02T16:20:00 --font_scale 2.0 --position bottom_right --units km/h
```

