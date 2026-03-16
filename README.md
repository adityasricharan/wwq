# Agentic WW1 & WW2 Trivia CLI

A Python command-line trivia game about World War 1 and World War 2. This game uses multiple Google Gemini AI agents to dynamically generate engaging, historically accurate trivia questions, complete with difficulty scaling and shareable, deterministic "seeds" to compete with friends.

## Prerequisites

- Python 3.9+
- A Google Gemini API Key

### Getting a Google API Key
Yes, the Google Gemini API is available for everyone! Google provides a generous free tier that is more than enough to play this quiz.

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click on **Get API key** in the left navigation menu.
4. Click **Create API key** and copy the generated key.

## Setup and Play (The Easy Way)

If you are on Windows, simply type `wwq` in your terminal or double-click the `wwq.bat` file! 

This script will automatically:
1. Set up your Python virtual environment.
2. Install the necessary dependencies quietly.
3. Prompt you for your Google API Key if it's your first time running the game.
4. Launch the game!

## Manual Setup Instructions (For Mac/Linux or advanced users)

1. **Clone or download the repository**, and navigate to the project folder:
   ```bash
   cd history_quiz
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**:
   - On Windows (PowerShell):
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - On macOS/Linux:
     ```bash
     source .venv/bin/activate
     ```

4. **Install the dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Set your API Key**:
   You can either set the environment variable in your terminal:
   ```bash
   export GOOGLE_API_KEY="your_api_key_here"
   ```
   Or, create a file named `.env` in the root of the `history_quiz` folder and add this line to it:
   ```env
   GOOGLE_API_KEY=your_api_key_here
   ```

6. **Play the Game**:
   ```bash
   python main.py
   ```

## How to Play

- **Topics**: You can leave the topic blank for general questions, or enter something specific like `"Spies"` or `"Naval Battles"`.
- **Game Seeds**: After a game starts, you'll be given a "Game Seed" (e.g., `eyJzIjogIjdTMzhDNiIsICJ0IjogInNwaWVzIn0=`). You can share this seed hash with anyone else running the game. If they enter that seed at the start menu, they will receive the exact same generated questions and difficulty scaling as you, allowing you to compete for the highest score!

## How to Share the Game

To distribute this game to your friends:

1. **Zip the Folder**: Compress the entire `history_quiz` folder into a `.zip` file. (Note: You can delete the `.venv` folder and `.env` file first to make the zip file much smaller, as the `wwq.bat` script will automatically recreate the environment for them!).
2. **Send it**: Send the `.zip` file via email, Discord, or any file-sharing service.
3. **Instructions**: Tell your friends on Windows to extract the folder, open it, and just double-click `wwq.bat`! If it's their first time, the script will simply ask them to paste in their free Google API key to start.
4. **Alternative (GitHub)**: You can also upload this entire folder to a public GitHub repository. Your friends can then download it by clicking "Code -> Download ZIP", or by `git cloning` it.
