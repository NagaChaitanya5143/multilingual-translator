# PolyGlot: Voice & Text Translator

A modern, responsive, and beautiful translator application built in Python using **Gradio**, supporting both **text-to-text** and **voice-to-voice** translation.

## Supported Languages
- 🇬🇧 English (`en`)
- 🇮🇳 Telugu (`te`)
- 🇮🇳 Tamil (`ta`)
- 🇪🇸 Spanish (`es`)
- 🇫🇷 French (`fr`)

---

## Features
1. **Text Translator**: Translate written text between any of the supported languages, with automatic pronunciation generation.
2. **Voice Translator**: Record your voice through your browser, transcribe it, translate it, and hear the translation spoken back in the target language.
3. **Responsive Web UI**: A beautiful dark/light soft-indigo theme, designed for ease of use.

---

## Installation & Setup

### Prerequisites
Make sure you have Python 3.8+ installed on your system.

### 1. Install Dependencies
Open your terminal in this project directory and run:
```bash
pip install -r requirements.txt
```

> [!NOTE]
> Since we use Gradio, all browser-based microphone recordings are handled cleanly. You do **not** need to install complex local audio system dependencies like `PyAudio`.

### 2. Run the Application
Start the application by running:
```bash
python app.py
```
This will start a local server. Open your web browser and navigate to:
```
http://127.0.0.1:7860
```

---

## GitHub Deployment Instructions

To push this repository to your GitHub account:

### 1. Create a Repository on GitHub
Go to [GitHub](https://github.com/) and create a new **empty** repository. Do **not** check the boxes to add a README, `.gitignore`, or License (since we have already created them locally). Copy the remote URL (e.g., `https://github.com/your-username/your-repo-name.git`).

### 2. Link and Push the Local Repository
Run the following commands in your local project directory terminal:

```bash
# Link your GitHub repository
git remote add origin <YOUR_GITHUB_REPOSITORY_URL>

# Rename current branch to main
git branch -M main

# Push your code to GitHub
git push -u origin main
```
If you are using Git Credential Manager, a window will pop up to sign in to your GitHub account.
