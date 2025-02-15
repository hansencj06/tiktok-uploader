#!/usr/bin/env python3
import os
import sys
import argparse
import requests
import time
import threading
import subprocess
import random
import string
import hashlib
from dotenv import load_dotenv
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

# Load environment variables from .env
load_dotenv()

# Define the redirect URI (must match TikTok's configuration exactly)
REDIRECT_URI = "http://localhost:8000/callback"

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("Error: OPENAI_API_KEY not set in environment.")
    sys.exit(1)

# TikTok API endpoints and credentials
TIKTOK_CLIENT_ID = os.getenv("TIKTOK_CLIENT_ID")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_TOKEN_URL = os.getenv("TIKTOK_TOKEN_URL", "https://open.tiktokapis.com/v2/oauth/token/")
# Direct Post Initialization endpoint (returns publish_id and upload_url)
TIKTOK_UPLOAD_INIT_URL = os.getenv("TIKTOK_UPLOAD_INIT_URL", "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/")
# Video Status endpoint for polling
TIKTOK_VIDEO_STATUS_URL = os.getenv("TIKTOK_VIDEO_STATUS_URL", "https://open.tiktokapis.com/v2/post/publish/inbox/video/status/")

# Constants for file handling and transcription
TRANSCRIPT_EXTENSION = ".txt"
WHISPER_MODEL = "whisper-1"
CHATGPT_MODEL = "gpt-3.5-turbo"

# PKCE Utility Functions
def generate_code_verifier(length=64):
    allowed = string.ascii_letters + string.digits + "-._~"
    return ''.join(random.choice(allowed) for _ in range(length))

def generate_code_challenge(code_verifier):
    return hashlib.sha256(code_verifier.encode('utf-8')).hexdigest()

def generate_state(length=16):
    allowed = string.ascii_letters + string.digits
    return ''.join(random.choice(allowed) for _ in range(length))

# OAuth Callback Server using Flask
from flask import Flask, request
auth_code_global = None
app = Flask(__name__)

@app.route('/callback')
def callback():
    global auth_code_global
    auth_code_global = request.args.get("code")
    return "Authentication successful. You can close this window."

def run_flask_server():
    app.run(host="localhost", port=8000, debug=False, use_reloader=False)

def get_auth_code_default():
    global auth_code_global
    auth_code_global = None
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = generate_state()
    flask_thread = threading.Thread(target=run_flask_server)
    flask_thread.daemon = True
    flask_thread.start()
    encoded_redirect_uri = quote_plus(REDIRECT_URI)
    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize/?"
        f"client_key={TIKTOK_CLIENT_ID}&redirect_uri={encoded_redirect_uri}&"
        f"response_type=code&scope=user.info.basic,video.upload&state={state}&"
        f"code_challenge={code_challenge}&code_challenge_method=S256"
    )
    print("OAuth URL being opened:", auth_url)
    print("Opening Safari for TikTok authentication...")
    subprocess.call(["open", "-a", "Safari", auth_url])
    while auth_code_global is None:
        time.sleep(1)
    return auth_code_global, code_verifier

def exchange_code_for_token(code, code_verifier):
    payload = {
        "client_key": TIKTOK_CLIENT_ID,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier
    }
    response = requests.post(TIKTOK_TOKEN_URL, data=payload)
    if response.status_code == 200:
        data = response.json()
        print(f"Token exchange response: {data}")
        access_token = data.get("access_token")
        if access_token:
            print("Access token obtained.")
            return access_token
        else:
            print("Error: No access token returned.")
            return None
    else:
        print("Error exchanging code for token:", response.text)
        return None

def get_tiktok_access_token():
    code, code_verifier = get_auth_code_default()
    if not code:
        print("Failed to retrieve auth code.")
        return None
    return exchange_code_for_token(code, code_verifier)

# Direct Post: Initialization Step
def initialize_video_post(file_size, access_token, caption):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    payload = {
        "post_info": {
            "title": caption,
            "privacy_level": "PUBLIC_TO_EVERYONE"
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,
            "total_chunk_count": 1
        }
    }
    print("Initializing video post...")
    response = requests.post(TIKTOK_UPLOAD_INIT_URL, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json().get("data", {})
        if "error" in response.json():
            error = response.json()["error"]
            if error.get("code") == "spam_risk_too_many_pending_share":
                print("Rate limit reached: Too many pending shares.")
                return "RATE_LIMIT", None
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        if publish_id and upload_url:
            if not upload_url.startswith("http"):
                upload_url = "https://" + upload_url
            print("Initialization successful. Publish ID:", publish_id)
            return publish_id, upload_url
        else:
            print("Error: Missing publish_id or upload_url in init response.")
            print("Response:", response.json())
            return None, None
    else:
        print("Error initializing video post:", response.text)
        return None, None

# Direct Post: Upload Call (using PUT with required headers including Content-Range)
def upload_video_file(upload_url, video_path, caption):
    print("Uploading video file via Direct Post...")
    file_size = os.path.getsize(video_path)
    with open(video_path, "rb") as video_file:
        file_data = video_file.read()
    headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(file_size),
        "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        "Accept": "application/json"
    }
    response = requests.put(upload_url, headers=headers, data=file_data)
    if response.status_code in (200, 201):
        print("Direct post upload successful.")
        return True
    else:
        print("Error in direct post upload. Status Code:", response.status_code)
        print("Response:", response.text)
        return False

# Poll Video Status
def poll_video_status(publish_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"publish_id": publish_id}
    while True:
        response = requests.get(TIKTOK_VIDEO_STATUS_URL, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json().get("data", {})
            status = data.get("status")
            print(f"Video status: {status}")
            if status != "PROCESSING_UPLOAD":
                return status
        elif response.status_code == 404:
            print("Received 404 from status endpoint; upload process is complete.")
            return "COMPLETED"
        else:
            print("Error polling video status:", response.text)
        time.sleep(5)

# Direct Post Flow
def direct_post_video(video_path, access_token):
    file_size = os.path.getsize(video_path)
    base, _ = os.path.splitext(video_path)
    txt_file = base + TRANSCRIPT_EXTENSION
    if not os.path.exists(txt_file):
        print(f"Error: Caption file {txt_file} not found.")
        return None
    with open(txt_file, "r", encoding="utf-8") as f:
        caption = f.read().strip()
    init_result = initialize_video_post(file_size, access_token, caption)
    if not init_result or init_result[0] == "RATE_LIMIT":
        return "RATE_LIMIT"
    publish_id, upload_url = init_result
    if not upload_video_file(upload_url, video_path, caption):
        return None
    print("Waiting for video processing to complete...")
    final_status = poll_video_status(publish_id, access_token)
    print("Final video status:", final_status)
    return publish_id

def get_tiktok_publish_id(video_path, access_token):
    return direct_post_video(video_path, access_token)

# Main Process and File Handling
def get_files_from_dir(directory):
    files = []
    for f in os.listdir(directory):
        if f.lower().endswith(".mp4"):
            files.append(os.path.join(directory, f))
    return files

def main():
    parser = argparse.ArgumentParser(description="Upload TikTok videos using the Direct Post method.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=str, help="Path to a single .mp4 file")
    group.add_argument("--dir", type=str, help="Path to a directory containing .mp4 files")
    args = parser.parse_args()

    files = []
    if args.file:
        files.append(os.path.abspath(args.file))
    else:
        directory = os.path.abspath(args.dir)
        if not os.path.isdir(directory):
            print("Error: Provided path is not a directory.")
            sys.exit(1)
        files = get_files_from_dir(directory)
    if not files:
        print("No .mp4 files found.")
        sys.exit(0)

    access_token = get_tiktok_access_token()
    if not access_token:
        print("TikTok authentication failed. Exiting.")
        sys.exit(1)

    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_file = {executor.submit(direct_post_video, f, access_token): f for f in files}
        for future in as_completed(future_to_file):
            result = future.result()
            results.append((future_to_file[future], result))

    success = [os.path.basename(f) for f, pub in results if pub and pub != "RATE_LIMIT"]
    failures = [(os.path.basename(f), pub) for f, pub in results if pub is None or pub == "RATE_LIMIT"]

    print("\n--- Upload Summary ---")
    print(f"Total files processed: {len(results)}")
    print(f"Successfully uploaded: {len(success)}")
    if success:
        print("Files uploaded successfully:")
        for name in success:
            print(f" - {name}")
    print(f"Failed uploads: {len(failures)}")
    if failures:
        print("Failed files:")
        for name, err in failures:
            print(f" - {name}: {err}")

if __name__ == "__main__":
    main()
