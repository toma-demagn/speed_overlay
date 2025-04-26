import argparse
import os
import subprocess
from datetime import datetime, timedelta, timezone

import gpxpy
from geopy.distance import geodesic


def get_video_info(video_file, ffmpeg_path='ffmpeg', debug_mode=False):
    import subprocess

    # Get width, height, frame rate
    cmd_stream = [
        ffmpeg_path.replace('ffmpeg', 'ffprobe'),
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,r_frame_rate',
        '-of', 'csv=p=0',
        video_file
    ]
    stream_info = subprocess.check_output(cmd_stream, universal_newlines=True).strip()
    width, height, fps_raw = stream_info.split(',')

    # Parse frame rate (e.g. '30000/1001')
    num, denom = map(int, fps_raw.split('/'))
    fps = num / denom

    # Get duration
    cmd_duration = [
        ffmpeg_path.replace('ffmpeg', 'ffprobe'),
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_file
    ]
    duration = float(subprocess.check_output(cmd_duration, universal_newlines=True).strip())

    return {
        'width': int(width),
        'height': int(height),
        'fps': fps,
        'duration': duration
    }


def parse_arguments():
    parser = argparse.ArgumentParser(description='Add speed overlay to video based on GPX data')
    parser.add_argument('video_file', help='Path to the MP4 video file')
    parser.add_argument('gpx_file', help='Path to the GPX file')
    parser.add_argument('--output', '-o', default=None, help='Output video file path')
    parser.add_argument('--time_delta', '-t', default=0, type=int,
                        help='Time delta in seconds to apply to video timestamps (can be negative)')
    parser.add_argument('--video_date', '-v', default=None,
                        help='Manually specify the video start date in ISO format (YYYY-MM-DDTHH:MM:SS)')
    parser.add_argument('--font_scale', '-f', default=1.5, type=float, help='Font scale for overlay text')
    parser.add_argument('--position', '-p', default='bottom_right',
                        choices=['top_left', 'top_right', 'bottom_left', 'bottom_right'],
                        help='Position of the speed overlay')
    parser.add_argument('--units', '-u', default='km/h', choices=['km/h', 'mph'], help='Speed units to display')
    parser.add_argument('--min_points', '-m', default=2, type=int,
                        help='Minimum points needed in the range to compute speed')
    parser.add_argument('--ffmpeg_path', default='ffmpeg', help='Path to ffmpeg executable if not in system PATH')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode with additional output')
    return parser.parse_args()


def debug_print(msg, debug):
    if debug:
        print(f"[DEBUG] {msg}")


def load_gpx(gpx_file):
    with open(gpx_file, 'r') as f:
        gpx = gpxpy.parse(f)
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append({'time': point.time, 'lat': point.latitude, 'lon': point.longitude})
    points.sort(key=lambda p: p['time'])
    return points


def get_speed(points, target_time, time_window=10, min_points=2):
    nearby = [p for p in points if abs((p['time'] - target_time).total_seconds()) <= time_window]
    if len(nearby) < min_points:
        return None
    distances = []
    times = []
    for i in range(len(nearby) - 1):
        d = geodesic((nearby[i]['lat'], nearby[i]['lon']), (nearby[i + 1]['lat'], nearby[i + 1]['lon'])).meters
        t = (nearby[i + 1]['time'] - nearby[i]['time']).total_seconds()
        distances.append(d)
        times.append(t)
    total_distance = sum(distances)
    total_time = sum(times)
    if total_time == 0:
        return None
    return (total_distance / total_time) * 3.6  # m/s to km/h


def convert_speed(speed, units):
    if speed is None:
        return None
    if units == 'mph':
        return speed * 0.621371
    return speed


def format_ass_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


def generate_ass(points, start_time, fps, duration, video_info, args):
    align_map = {
        'top_left': 7,
        'top_right': 9,
        'bottom_left': 1,
        'bottom_right': 3
    }
    align = align_map[args.position]

    header = f"""[Script Info]
Title: Speed Overlay
ScriptType: v4.00+
PlayResX: {video_info['width']}
PlayResY: {video_info['height']}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{int(48 * args.font_scale)},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,{align},10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    interval = 1 / fps
    current = start_time
    frame = 0
    while frame * interval < duration:
        speed = get_speed(points, current, min_points=args.min_points)
        speed = convert_speed(speed, args.units)
        if speed is not None:
            text = f"Speed: {speed:.1f} {args.units}"
        else:
            text = "Speed: N/A"

        start = format_ass_timestamp((current - start_time).total_seconds())
        end = format_ass_timestamp((current - start_time + timedelta(seconds=interval)).total_seconds())

        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

        frame += 1
        current += timedelta(seconds=interval)

    return header + "\n".join(events)


def get_video_duration(video_file, ffmpeg_path):
    try:
        cmd = [ffmpeg_path.replace('ffmpeg', 'ffprobe'), '-v', 'error', '-show_entries', 'format=duration', '-of',
               'default=noprint_wrappers=1:nokey=1', video_file]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"ERROR: Could not get video duration: {e}")
        return None


def get_video_fps(video_file, ffmpeg_path):
    try:
        cmd = [ffmpeg_path.replace('ffmpeg', 'ffprobe'), '-v', 'error', '-select_streams', 'v:0', '-show_entries',
               'stream=r_frame_rate', '-of', 'csv=p=0', video_file]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                                check=True)
        num, denom = map(int, result.stdout.strip().split('/'))
        return num / denom
    except Exception as e:
        print(f"ERROR: Could not get video fps: {e}")
        return 30.0  # Default to 30 FPS


def main():
    args = parse_arguments()
    video_info = get_video_info(args.video_file, args.ffmpeg_path, args.debug)
    debug_print("Parsing GPX...", args.debug)
    gpx_points = load_gpx(args.gpx_file)

    debug_print("Getting video properties...", args.debug)
    duration = get_video_duration(args.video_file, args.ffmpeg_path)
    fps = get_video_fps(args.video_file, args.ffmpeg_path)

    if args.video_date:
        video_start_time = datetime.fromisoformat(args.video_date.rstrip('Z')).replace(tzinfo=timezone.utc)
    else:
        video_start_time = gpx_points[0]['time'].astimezone(timezone.utc)
    video_start_time += timedelta(seconds=args.time_delta)

    debug_print(f"Start time: {video_start_time.isoformat()}", args.debug)
    debug_print(f"Duration: {duration:.2f} seconds", args.debug)
    debug_print(f"FPS: {fps:.2f}", args.debug)

    ass_path = os.path.abspath("overlay.ass")  # Write overlay.ass in your working directory

    debug_print(f"Generating ASS overlay at {ass_path}", args.debug)

    ass_content = generate_ass(gpx_points, video_start_time, fps, duration, video_info, args)

    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

        debug_print(f"Generating ASS overlay at {ass_path}", args.debug)

        output_file = args.output
        if not output_file:
            base, ext = os.path.splitext(args.video_file)
            output_file = f"{base}_with_speed{ext}"

        debug_print(f"Output file will be: {output_file}", args.debug)

        safe_ass_path = ass_path.replace('\\', '/')
        cmd = [
            args.ffmpeg_path,
            '-i', args.video_file,
            '-vf', f"ass={safe_ass_path}",
            '-c:v', 'libx264',
            '-crf', '18',
            '-preset', 'medium',
            '-c:a', 'copy',
            '-y',
            output_file
        ]
        debug_print(f"Running FFmpeg: {' '.join(cmd)}", args.debug)

        # Run FFmpeg
        subprocess.run(cmd, check=True)

    print(f"✅ Done! Output saved to: {output_file}")


if __name__ == "__main__":
    main()
