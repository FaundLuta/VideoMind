# 📹 VideoMind

**VideoMind** is a professional desktop application designed to transform video content into actionable intelligence. By leveraging local AI for transcription and high-speed LLMs for summarization, it allows users to quickly digest long-form videos and interact with them via an intelligent chat interface.

![Version](https://img.shields.io/badge/version-1.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

## ✨ Features

*   **Multi-Source Support**: Process local video files (`.mp4`, `.mkv`, `.mov`, etc.) or download audio directly from YouTube/URLs.
*   **AI Transcription**: Uses OpenAI's **Whisper** (Local) for highly accurate speech-to-text.
*   **Groq Acceleration**: Leverages **Groq Cloud** for near-instant summaries using state-of-the-art models like Llama 3.
*   **Interactive Chat**: Ask questions about the video content, generate social media captions, or create quizzes based on the transcript.
*   **Session Management**: Automatically saves your transcripts and chat histories in a local SQLite database.
*   **Modern UI**: A clean, Material-inspired Google-style interface built with Python's Tkinter.

## 🚀 Getting Started

### Prerequisites

1.  **FFmpeg**: Required for audio extraction.
    *   **Windows**: Download from ffmpeg.org and add to PATH.
    *   **macOS**: `brew install ffmpeg`
    *   **Linux**: `sudo apt install ffmpeg`
2.  **Groq API Key**: Get a free key from the Groq Console.

### Installation (Development)

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/videomind.git
    cd videomind
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Setup Environment Variables**:
    Create a `.env` file in the root directory (refer to `.env.example`):
    ```env
    GROQ_API_KEY=your_actual_api_key_here
    ```

4.  **Run the app**:
    ```bash
    python app.py
    ```

## 📦 Distribution

To package the application for Windows:

1.  Run PyInstaller to create the distribution folder:
    ```bash
    python -m PyInstaller --noconsole --onedir --name "VideoMind" --add-data ".env;." --collect-all whisper app.py
    ```
2.  Include `ffmpeg.exe` and `ffprobe.exe` in the `dist/VideoMind` folder.
3.  Use the provided `videomind.iss` script with **Inno Setup Compiler** to generate the final installer.

## 🛠 Built With

*   **Python 3.x**
*   **Tkinter**: GUI Framework.
*   **OpenAI Whisper**: Local Speech Recognition.
*   **Groq SDK**: High-speed LLM inference.
*   **yt-dlp**: Video metadata and audio downloading.
*   **SQLite**: Local data persistence.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---
*Developed with ❤️ by Somto*