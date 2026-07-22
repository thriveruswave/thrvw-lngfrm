"""
Retroactively generate & upload thumbnails for previously uploaded videos.
Usage: python upload_retro_thumbnails.py <video_id> [<video_topic>] [<video_id2> <video_topic2>]
"""

import os
import sys
import base64
import io
from pathlib import Path
import time
import requests
from PIL import Image
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
def get_authenticated_service():
    client_id = os.environ['YT_CLIENT_ID']
    client_secret = os.environ['YT_CLIENT_SECRET']
    refresh_token = os.environ['YT_REFRESH_TOKEN']
    creds = Credentials(
        None, refresh_token=refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id, client_secret=client_secret,
        scopes=['https://www.googleapis.com/auth/youtube']
    )
    creds.refresh(Request())
    return build('youtube', 'v3', credentials=creds)


def generate_thumbnail(topic, output_path):
    print(f'[thumb] Generating thumbnail for: {topic}')

    pollinations_key = os.environ.get('POLLINATIONS_API_KEY') or os.environ.get('OPENAI_API_KEY')
    if not pollinations_key:
        print('[thumb] ❌ No POLLINATIONS_API_KEY or OPENAI_API_KEY set')
        return None

    prompt = (
        f'YouTube thumbnail for historical video {topic}, '
        f'ancient women, cinematic, dramatic lighting, gold colors, 16:9'
    )

    for attempt in range(4):
        try:
            resp = requests.post("https://gen.pollinations.ai/v1/images/generations", json={
                "model": "gpt-image-2",
                "prompt": prompt,
                "n": 1,
                "size": "1792x1024",
            }, headers={"Authorization": f"Bearer {pollinations_key}"}, timeout=300)
            if resp.status_code == 200 and resp.json().get("data"):
                raw = base64.b64decode(resp.json()["data"][0]["b64_json"])
                if raw:
                    img = Image.open(io.BytesIO(raw)).convert("RGB")
                    img = img.resize((1920, 1080), Image.LANCZOS)
                    thumb_bytes = io.BytesIO()
                    quality = 85
                    img.save(thumb_bytes, format='JPEG', quality=quality)
                    while thumb_bytes.tell() > 2097152 and quality > 10:
                        quality -= 10
                        thumb_bytes = io.BytesIO()
                        img.save(thumb_bytes, format='JPEG', quality=quality)
                    thumb_bytes.seek(0)
                    with open(output_path, 'wb') as f:
                        f.write(thumb_bytes.read())
                    thumb_bytes.seek(0)
                    print(f'[thumb] Generated ({output_path.stat().st_size // 1024}KB)')
                    return thumb_bytes
        except Exception as e:
            msg = str(e)[:60]
            if attempt < 3:
                print(f'[thumb] Attempt {attempt+1} failed ({msg}), retrying...')
                time.sleep(10 * (attempt + 1))
            else:
                print(f'[thumb] ❌ Failed after 4 attempts: {msg}')

    return None


def upload_thumbnail(youtube, video_id, thumb_bytes):
    print(f'[thumb] Uploading thumbnail to video {video_id}...')
    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaIoBaseUpload(thumb_bytes, mimetype='image/jpeg', resumable=False)
    ).execute()
    print(f'[thumb] Uploaded to https://youtube.com/watch?v={video_id}')


def main():
    args = sys.argv[1:]
    if len(args) < 1 or len(args) % 2 != 0:
        print('Usage: python upload_retro_thumbnails.py <video_id> <topic> [<video_id2> <topic2> ...]')
        sys.exit(1)

    videos = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]

    print(f'[thumb] Processing {len(videos)} video(s)')
    youtube = get_authenticated_service()

    for video_id, topic in videos:
        thumb_path = Path(f'/tmp/thumb_{video_id}.jpg')
        try:
            thumb_bytes = generate_thumbnail(topic, thumb_path)
            if thumb_bytes:
                upload_thumbnail(youtube, video_id, thumb_bytes)
            else:
                print(f'[thumb] Skipping {video_id} — thumbnail generation failed')
        except Exception as e:
            print(f'[thumb] Failed for {video_id}: {e}')
        finally:
            if thumb_path.exists():
                thumb_path.unlink()

    print('[thumb] Done!')


if __name__ == '__main__':
    main()
