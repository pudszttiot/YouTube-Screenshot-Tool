import os
import json
import subprocess
import tempfile
import base64
from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')  # Change this!

def get_youtube_info(url):
    """Get video title, duration, and the best video stream URL using cookies if available."""
    cookies_env = os.environ.get('YOUTUBE_COOKIES')
    cookies_path = None

    try:
        if cookies_env:
            # Decode the base64 cookies and write to a temporary file
            cookies_data = base64.b64decode(cookies_env).decode('utf-8')
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(cookies_data)
                cookies_path = f.name

        # Base command with optional cookies
        base_cmd = ['yt-dlp', '--no-check-certificate']
        if cookies_path:
            base_cmd += ['--cookies', cookies_path]

        # Get video info (title, duration)
        cmd = base_cmd + ['--dump-json', '--skip-download', url]
        output = subprocess.check_output(cmd, stderr=subprocess.PIPE, text=True)
        info = json.loads(output)
        title = info.get('title', 'Unknown Title')
        duration = info.get('duration', 0)

        # Get the best video stream URL
        format_cmd = base_cmd + ['-f', 'bestvideo', '--get-url', url]
        video_url = subprocess.check_output(format_cmd, stderr=subprocess.PIPE, text=True).strip()
        if not video_url:
            # Fallback to 'best' combined format
            format_cmd = base_cmd + ['-f', 'best', '--get-url', url]
            video_url = subprocess.check_output(format_cmd, stderr=subprocess.PIPE, text=True).strip()

        return title, duration, video_url

    except subprocess.CalledProcessError as e:
        print(f"yt-dlp error: {e.stderr}")
        return None, None, None

    finally:
        # Clean up temporary cookies file
        if cookies_path and os.path.exists(cookies_path):
            os.unlink(cookies_path)

def extract_frame(video_url, timestamp, output_format='jpg', scale=None, quality=None):
    """
    Extract a frame at the given timestamp.
    - output_format: 'jpg' or 'png'
    - scale: if provided, scale the image (e.g., '320:-1' for width 320, height auto)
    - quality: for JPEG, 1-31 (1=best); for PNG, compression 0-9 (0=best)
    """
    if not video_url:
        return None

    if output_format == 'jpg':
        suffix = '.jpg'
        if quality is None:
            quality_args = ['-q:v', '1']   # highest quality
        else:
            quality_args = ['-q:v', str(quality)]
    else:
        suffix = '.png'
        if quality is None:
            quality_args = ['-compression_level', '0']   # best PNG quality (largest)
        else:
            quality_args = ['-compression_level', str(quality)]

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        output_path = tmp.name

    try:
        cmd = ['ffmpeg', '-ss', str(timestamp), '-i', video_url, '-frames:v', '1']
        if scale:
            cmd += ['-vf', f'scale={scale}']
        cmd += quality_args + ['-y', output_path]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg error: {e.stderr}")
        return None

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form.get('url')
        if not url:
            flash('Please enter a YouTube URL.')
            return redirect(url_for('index'))
        if 'youtube.com' not in url and 'youtu.be' not in url:
            flash('Please enter a valid YouTube URL.')
            return redirect(url_for('index'))

        title, duration, video_url = get_youtube_info(url)
        if not title:
            flash('Could not retrieve video information. Check the URL.')
            return redirect(url_for('index'))

        session['video_url'] = url
        session['video_title'] = title
        session['duration'] = duration
        session['stream_url'] = video_url
        return redirect(url_for('video'))
    return render_template('index.html')

@app.route('/video')
def video():
    if 'video_url' not in session:
        flash('No video loaded. Please enter a URL first.')
        return redirect(url_for('index'))
    return render_template('video.html',
                           video_url=session['video_url'],
                           title=session['video_title'],
                           duration=session['duration'])

@app.route('/preview', methods=['POST'])
def preview():
    """Extract a small, low-quality frame for preview."""
    if 'stream_url' not in session:
        return jsonify({'error': 'No video stream available'}), 400

    timestamp = request.form.get('timestamp')
    if not timestamp:
        return jsonify({'error': 'Timestamp missing'}), 400
    try:
        timestamp = float(timestamp)
    except ValueError:
        return jsonify({'error': 'Invalid timestamp'}), 400

    video_url = session['stream_url']
    # Scale to width 320 and use lower JPEG quality for speed
    frame_path = extract_frame(video_url, timestamp, output_format='jpg', scale='320:-1', quality=8)
    if frame_path:
        return send_file(frame_path, mimetype='image/jpeg')
    else:
        return jsonify({'error': 'Failed to extract preview'}), 500

@app.route('/capture', methods=['POST'])
def capture():
    """Extract a high-quality frame."""
    if 'stream_url' not in session:
        return jsonify({'error': 'No video stream available'}), 400

    timestamp = request.form.get('timestamp')
    output_format = request.form.get('format', 'jpg')
    if not timestamp:
        return jsonify({'error': 'Timestamp missing'}), 400
    try:
        timestamp = float(timestamp)
    except ValueError:
        return jsonify({'error': 'Invalid timestamp'}), 400

    video_url = session['stream_url']
    frame_path = extract_frame(video_url, timestamp, output_format=output_format)
    if frame_path:
        mime = 'image/jpeg' if output_format == 'jpg' else 'image/png'
        filename = f'screenshot.{output_format}'
        return send_file(frame_path, mimetype=mime, as_attachment=True, download_name=filename)
    else:
        return jsonify({'error': 'Failed to extract frame. Ensure ffmpeg is installed and the video URL is accessible.'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
