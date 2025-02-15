#!/usr/bin/env python3
import os
import sys
import argparse
import requests
import subprocess
import random
import string
import hashlib
import time
from dotenv import load_dotenv
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

# Load environment variables from .env
load_dotenv()

# --- Constants ---
WHISPER_MODEL = "whisper-1"
CHATGPT_MODEL = "gpt-3.5-turbo"
TRANSCRIPT_EXTENSION = ".txt"

# --- OpenAI API Key ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("Error: OPENAI_API_KEY not set in environment.")
    sys.exit(1)

# --- Google Drive Folder ID ---
# Set this in your .env file to the folder ID of "My Drive/tiktok movie descriptions/"
TIKTOK_DESCRIPTIONS_FOLDER_ID = os.getenv("TIKTOK_DESCRIPTIONS_FOLDER_ID")
if not TIKTOK_DESCRIPTIONS_FOLDER_ID:
    print("Error: TIKTOK_DESCRIPTIONS_FOLDER_ID not set in environment.")
    sys.exit(1)

# --- Google Drive Authentication ---
def authenticate_drive():
    gauth = GoogleAuth()
    gauth.LocalWebserverAuth()  # Opens browser for authentication.
    drive = GoogleDrive(gauth)
    return drive

# --- Video Transcription using OpenAI's Whisper API ---
def transcribe_video(video_path):
    print(f"Transcribing video: {video_path}")
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    data = {"model": WHISPER_MODEL, "response_format": "verbose_json"}
    try:
        with open(video_path, "rb") as f:
            files = {"file": (os.path.basename(video_path), f, "video/mp4")}
            response = requests.post(url, headers=headers, data=data, files=files)
        if response.status_code != 200:
            print(f"Error during transcription: {response.status_code}\n{response.text}")
            return None
        transcript = response.json().get("text", "")
        print("Transcription complete.")
        return transcript
    except Exception as e:
        print(f"Exception during transcription: {e}")
        return None

# --- Video Description Generation using ChatGPT ---
def generate_description(transcript):
    print("Generating video description...")
    prompt = (
        "Generate a very short and sweet TikTok video description based on the following transcript. "
        "Include a bunch of creative hashtags at the end:\n\n" + transcript
    )
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    json_payload = {
        "model": CHATGPT_MODEL,
        "messages": [
            {"role": "system", "content": "You are a creative content assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 150
    }
    try:
        response = requests.post(url, headers=headers, json=json_payload)
        if response.status_code != 200:
            print(f"Error generating description: {response.status_code}\n{response.text}")
            return None
        description = response.json()["choices"][0]["message"]["content"].strip()
        print("Video description generated.")
        return description
    except Exception as e:
        print(f"Exception generating description: {e}")
        return None

# --- Save Description to Text File ---
def save_description(video_path, description):
    base, _ = os.path.splitext(video_path)
    txt_path = base + TRANSCRIPT_EXTENSION
    try:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(description)
        print(f"Description saved to {txt_path}")
        return txt_path
    except Exception as e:
        print(f"Error saving description: {e}")
        return None

# --- Upload Text File to Google Drive ---
def upload_to_drive(drive, file_path):
    print(f"Uploading {file_path} to Google Drive folder with ID {TIKTOK_DESCRIPTIONS_FOLDER_ID}...")
    try:
        gfile = drive.CreateFile({
            'title': os.path.basename(file_path),
            'parents': [{'id': TIKTOK_DESCRIPTIONS_FOLDER_ID}]
        })
        gfile.SetContentFile(file_path)
        gfile.Upload()
        print(f"File uploaded to Google Drive with ID: {gfile['id']}")
        return gfile['id']
    except Exception as e:
        print(f"Error uploading file to Google Drive: {e}")
        return None

# --- Process a Single File ---
def process_file(video_path, drive):
    print(f"Processing file: {video_path}")
    base, _ = os.path.splitext(video_path)
    txt_path = base + TRANSCRIPT_EXTENSION
    if os.path.exists(txt_path):
        print(f"Skipping {video_path} because {txt_path} already exists.")
        return (video_path, True, "Already processed")
    transcript = transcribe_video(video_path)
    if transcript is None:
        return (video_path, False, "Transcription failed")
    description = generate_description(transcript)
    if description is None:
        return (video_path, False, "Description generation failed")
    txt_path = save_description(video_path, description)
    if txt_path is None:
        return (video_path, False, "Saving description failed")
    drive_file_id = upload_to_drive(drive, txt_path)
    if drive_file_id is None:
        return (video_path, False, "Upload to Drive failed")
    return (video_path, True, drive_file_id)

# --- Main Process ---
def main():
    parser = argparse.ArgumentParser(description="Transcribe .mp4 files and upload generated text files to Google Drive.")
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
        for f in os.listdir(directory):
            if f.lower().endswith(".mp4"):
                files.append(os.path.join(directory, f))
    if not files:
        print("No .mp4 files found.")
        sys.exit(0)

    # Filter out files that already have corresponding .txt files.
    files_to_process = []
    for f in files:
        base, _ = os.path.splitext(f)
        txt_file = base + TRANSCRIPT_EXTENSION
        if os.path.exists(txt_file):
            print(f"Skipping {f} because {txt_file} already exists.")
        else:
            files_to_process.append(f)
    if not files_to_process:
        print("All files have already been processed.")
        sys.exit(0)

    drive = authenticate_drive()
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_file = {executor.submit(process_file, f, drive): f for f in files_to_process}
        for future in as_completed(future_to_file):
            results.append(future.result())

    success = [os.path.basename(f) for f, s, _ in results if s]
    failures = [(os.path.basename(f), err) for f, s, err in results if not s]

    print("\n--- Processing Summary ---")
    print(f"Total files processed: {len(results)}")
    print(f"Successfully processed: {len(success)}")
    if success:
        print("Files processed successfully:")
        for name in success:
            print(f" - {name}")
    print(f"Failed processing: {len(failures)}")
    if failures:
        print("Failed files:")
        for name, err in failures:
            print(f" - {name}: {err}")

if __name__ == "__main__":
    main()
