# WW1 & WW2 Agentic Trivia CLI

A completely offline, highly advanced Python command-line trivia game exploring World War 1 and World War 2 history. 

This game utilizes a massive local encrypted knowledge bank consisting of **2,046 strictly factual questions**, guaranteeing endless replayability without ever seeing a duplicated question. The entire database was dynamically generated and authenticated by Google's Gemini 2.5 Flash AI, but the game itself runs entirely 100% offline.

## Features

- **Massive Offline Bank:** 2,046 factual, unique questions encrypted via Fernet cryptography. No API key required by default!
- **Dynamic Scoring Penalties:** Questions are graded on a strict 1-5 difficulty curve. Miss a Level 5 (Insane) question and you lose 1 point. Miss a Level 1 (Easy) question and you lose 5 points.
- **End-Game Review Matrix:** A beautiful `Rich.Table` printout at the end of every game breaking down exactly what you missed, the correct answers, and your resulting 1-10 absolute "Historical Knowledge Scale".
- **Zero Repetition Engine:** A deterministic `seen_questions` algorithm ensures you will *never* see the same question twice in a single sitting.
- **Over-The-Air (OTA) Updates:** The game automatically pings GitHub for centralized question-bank updates every time it boots.
- **AI Expansion Integration:** Optionally, plug in a Google, OpenAI, or local Ollama API key via the settings menu to expand the game beyond the curated offline bank!

## Setup and Play

Running the game is incredibly simple on both Windows and MacOS/Linux.

### Windows
Just double-click the `wwq.bat` file, or type `.\wwq.bat` in your PowerShell terminal!

### MacOS & Linux
Run the bash script from your terminal:
```bash
chmod +x wwq.sh
./wwq.sh
```

### What happens in the background?
1. The script will automatically fetch any Over-The-Air updates for the question bank from GitHub.
2. It provisions an isolated Python virtual environment (`.venv`).
3. It installs all necessary styling and decryption dependencies quietly in the background.
4. It launches the game interface.

## How to Play

### 1. The Main Menu
When the game boots, you will be greeted by the Start Menu. You can immediately press **Enter** to dive into a randomly seeded 20-question quiz.

```text
================================================================================
                           WW1 & WW2 TRIVIA CLI                                 
================================================================================
[INFO] Offline encrypted bank loaded successfully.

Commands:
  (Press Enter) to start a new game with a random seed.
  (Type a 6-character Hash) to play a specific deterministic game.
  's' for Settings
  'exit' to quit

Enter command: 
```

### 2. Gameplay & Sharing Seeds
Once a game starts, you'll be given a "Game Seed" (e.g., `7S38D6`). You can share this seed hash with anyone else running the game. If they enter that seed at the start menu, they will receive the exact same generated questions, allowing you to easily compete for the highest score!

```text
--- Game Started! ---
Your unique game seed is: 7S38D6
---------------------
```

### 3. The Settings Menu
If you want to configure your play experience, type `s` at the Main Menu.

```text
--- Settings ---
Current Settings:
Provider: local_bank
Model: questions.enc

Do you want to change the LLM provider? (local_bank, gemini, ollama, openai) [local_bank]: 
```

From here, you can switch from the `local_bank` to `gemini` or `ollama`. If you choose an external API, the game will seamlessly prompt you for an API Key or local Model name, enabling you to dynamically generate infinite unique trivia!

### 4. End-Game Review
The game automatically caps at a perfect **20 Questions**. You can also type `exit` at any prompt to securely leave the game. Once completed, the engine calculates your score and prints the Review Matrix:

```text
                              End of Game Review                              
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ #  ┃ Your Answer         ┃ Correct Answer      ┃ Difficulty ┃ Score Effect ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ 1  │ Alan Turing         │ Alan Turing         │ 2          │ +20.0        │
│ 2  │ Operation Torch     │ Operation Husky     │ 4          │ -1.25        │
│ 3  │ The Maginot Line    │ The Maginot Line    │ 2          │ +20.0        │
└────┴─────────────────────┴─────────────────────┴────────────┴──────────────┘

Historical Knowledge Scale
Grade: 8.0 / 10
Your Score: 38.75
Theoretical Maximum: 80.0
```

---

## Developer Guide: Re-seeding the Knowledge Bank

If you wish to update the 2,046 questions or generate a new specialized bank (e.g., Vietnam War):

1. **Get an API Key:** Add your Gemini API Key to `.env`.
2. **Configure `generate_db.py`:** Update the prompt or the `target_questions` count.
3. **Run the Generator:**
   ```bash
   python generate_db.py
   ```
4. **Encrypt the Output:**
   ```bash
   python encrypt_db.py
   ```
5. **Update the Secret Key:** Copy the new encryption key printed in your terminal and update the `DATABASE_DECRYPTION_KEY` inside `database.py`.

## Troubleshooting

- **"Module Not Found":** Ensure you are running the game through `wwq.bat` or `wwq.sh`, which automatically handles the virtual environment and `pip install`.
- **API Errors (In Online Mode):** Check your internet connection and ensure your `.env` key is valid. The game will gracefully fall back to the `local_bank` if an online connection fails.
- **OTA Update Fails:** If the GitHub ping fails, the game will simply skip the update and load your last saved `questions.enc`.

## License & Contributing

This project is open-source. Feel free to submit Pull Requests to improve the historical accuracy of the question bank or to add new LLM providers!

---
*Created with ❤️ by the WW-Trivia community.*

