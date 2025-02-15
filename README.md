# TikTok Video Uploader & Transcriber

This project provides Python scripts for two main tasks:

1. **Uploading TikTok Videos:**  
   The `upload.py` script uses TikTok’s Direct Post API to initialize an upload, send the video file, and poll for its processing status until complete.

2. **Transcribing Videos & Uploading Descriptions to Google Drive:**  
   The `transcribe.py` script transcribes a TikTok video using OpenAI’s Whisper API, generates a creative, hashtag-rich description using ChatGPT, and uploads the resulting text file (saved with the same base name as the video) to Google Drive.

---

## Overview

- **Direct Post Video Upload:**  
  - **Initialization:**  
    A POST request is sent to `/v2/post/publish/inbox/video/init/` with video metadata and a caption (read from a text file with the same base name as the video).  
  - **Upload:**  
    The video is then uploaded via a PUT request to the `upload_url` provided by the initialization call. This request includes the following headers:
    - `Content-Type: video/mp4`
    - `Content-Length: <file size in bytes>`
    - `Content-Range: bytes 0-{file_size-1}/{file_size}`
    - `Accept: application/json`
  - **Polling:**  
    The script polls the video status endpoint every 5 seconds until the status is no longer `"PROCESSING_UPLOAD"` (or a 404 is returned, indicating completion).

- **Transcription & Description Generation:**  
  - The script uses OpenAI’s Whisper API to transcribe the video.
  - ChatGPT is then used to generate a short, creative TikTok video description with multiple hashtags.
  - The generated description is saved as a text file with the same base name as the video (e.g. `video.mp4` produces `video.txt`).

- **Google Drive Integration (for `transcribe.py`):**  
  - The generated text file is uploaded to Google Drive using PyDrive2.  
  - **Note:** Ensure you have set up your Google Drive API credentials and placed your `client_secrets.json` in the project root.

- **Parallel Processing:**  
  - When processing a directory, the scripts support concurrent processing of up to 4 files.

---

## Requirements

- **Python 3.7+**
- **Python Libraries:**
  - `requests`
  - `python-dotenv`
  - `Flask`
  - `PyDrive2`
- A valid **OpenAI API key**
- TikTok Developer credentials (Client ID & Client Secret) for accessing the Direct Post API
- For Google Drive integration (in `transcribe.py`):
  - A Google Cloud project with the Drive API enabled
  - OAuth2 credentials downloaded as `client_secrets.json` placed in the project root

---

## Installation

1. **Clone the Repository:**

   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Install Dependencies:**

   Create a `requirements.txt` file with the following content if it doesn’t exist:

   ```txt
   requests
   python-dotenv
   Flask
   PyDrive2
   ```

   Then run:

   ```bash
   pip install -r requirements.txt
   ```

   *Alternatively, install manually:*

   ```bash
   pip install requests python-dotenv Flask PyDrive2
   ```

---

## Configuration

1. **Create a `.env` File:**

   In the project root, create a `.env` file with the following (replace placeholders with your actual keys):

   ```dotenv
   OPENAI_API_KEY=your_openai_api_key_here
   TIKTOK_CLIENT_ID=your_tiktok_client_id_here
   TIKTOK_CLIENT_SECRET=your_tiktok_client_secret_here
   TIKTOK_TOKEN_URL=https://open.tiktokapis.com/v2/oauth/token/
   TIKTOK_UPLOAD_INIT_URL=https://open.tiktokapis.com/v2/post/publish/inbox/video/init/
   TIKTOK_VIDEO_STATUS_URL=https://open.tiktokapis.com/v2/post/publish/inbox/video/status/
   ```

2. **Set Up Google Drive API (for `transcribe.py`):**

   - Create a Google Cloud project and enable the Google Drive API.
   - Configure the OAuth consent screen.
   - Create OAuth Client Credentials (choose "Desktop app").
   - Download the `client_secrets.json` file and place it in the project directory.

---

## Usage

### TikTok Video Upload (`upload.py`)

- **Upload a Single Video:**

  ```bash
  python upload.py --file path/to/video.mp4
  ```

- **Upload All Videos in a Directory (Processes up to 4 concurrently):**

  ```bash
  python upload.py --dir path/to/directory
  ```

### Video Transcription & Google Drive Upload (`transcribe.py`)

- **Transcribe a Single Video & Upload the Description:**

  ```bash
  python transcribe.py --file path/to/video.mp4
  ```

- **Transcribe All Videos in a Directory & Upload Descriptions:**

  ```bash
  python transcribe.py --dir path/to/directory
  ```

*Note: In both workflows, the generated text file is saved with the same basename as the video (e.g. `video.mp4` produces `video.txt`). If the text file already exists, the script assumes that file has already been processed.*

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for improvements or bug fixes.

---

## Contact

For questions or support, please contact [Your Name or Email].
