"""
Retroactively generate & upload thumbnails for previously uploaded videos.
Usage: python upload_retro_thumbnails.py <video_id> [<video_topic>] [<video_id2> <video_topic2>]
"""

import os
import sys
import base64
import io
from pathlib import Path
import requests
from PIL import Image
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import openai


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
    client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    prompt = (
        f'YouTube thumbnail for historical video {topic}, '
        f'ancient women, cinematic, dramatic lighting, gold colors, 16:9'
    )
    resp = client.images.generate(
        model='gpt-image-2', prompt=prompt,
        size='1792x1024', quality='high', n=1
    )
    raw = None
    if resp.data[0].url:
        raw = requests.get(resp.data[0].url, timeout=60).content
    elif resp.data[0].b64_json:
        raw = base64.b64decode(resp.data[0].b64_json)
    img = Image.open(io.BytesIO(raw))
    # Compress to stay under 2MB
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
            upload_thumbnail(youtube, video_id, thumb_bytes)
        except Exception as e:
            print(f'[thumb] Failed for {video_id}: {e}')
        finally:
            if thumb_path.exists():
                thumb_path.unlink()

    print('[thumb] Done!')


if __name__ == '__main__':
    main()
