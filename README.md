# WW1 & WW2 Agentic Trivia CLI

A completely offline, highly advanced Python command-line trivia game exploring World War 1 and World War 2 history. 

This game utilizes a massive local encrypted knowledge bank consisting of **2,046 strictly factual questions**, guaranteeing endless replayability without ever seeing a duplicated question. The entire database was dynamically generated and authenticated by Google's Gemini 2.5 Flash AI, but the game itself runs entirely 100% offline.

## Features

- **Two Dynamic Game Modes:** Play defensively in **Adaptive Mode**, where questions get harder as you answer correctly, or play deterministically with fixed difficulty in **VS Mode**!
- **Massive Offline Bank:** 2,046 factual, unique questions encrypted via Fernet cryptography. No API key required by default!
- **Custom Question Banks:** Generate your own offline, encrypted question banks around any specific topic (`banks/<slug>.enc`) and swap them via settings.
- **Dynamic Scoring Penalties:** Questions are graded on a strict 1-5 difficulty curve. Miss a Level 5 (Insane) question and you lose 1.25 points. Miss a Level 1 (Easy) question and you lose 5 points.
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
When the game boots, you will be greeted by the Start Menu. You can immediately press **Enter** to dive into a quiz, where you can configure the Game Mode and Question Length.

### 2. Game Modes
The CLI now offers two distinct game modes:

#### 🕹️ Adaptive Mode (Single Player)
- **Concept:** The game intelligently adjusts difficulty based on your performance. Get questions right, and the game throws harder questions at you. Get them wrong, and it scales back to easier questions.
- **Mechanics:** Questions are drawn dynamically, checking your global history file to ensure less-frequently-seen questions are prioritized.
- **Seeds Hidden:** In this mode, no seeds are shared or required.

#### ⚔️ VS Mode (Multiplayer/Deterministic)
- **Concept:** A truly deterministic mode for competing with friends! Provide a shared random hash or let the game generate one. 
- **Mechanics:** The difficulty remains totally flat. All questions are drawn completely upfront at runtime based *strictly* on the shared seed and the total question count. 
- **Seeds Required:** Every VS mode game has a prefixed seed like `VS:7S38D6`. By sharing this short alphanumeric key, your friend will face the **exact same questions in the exact same order** allowing for pure competitive high-score chasing.

---

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

#### 🏦 Select Active Bank
If you have created custom banks (see below), they will be listed in an internal `banks/index.json` registry. Under the settings menu, you can navigate to **Manage Question Bank** -> **Select Active Bank** to swap out the official WW1/WW2 bank for any custom bank of your creation.

---

### 4. End-Game Review
The game length is configurable at start, with a default of **20 Questions**. You can also type `exit` at any prompt to securely leave the game. Once completed, the engine calculates your score and prints the Review Matrix:

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

## Question Bank Management

### How Updates Work

Every time you launch the game via `wwq.bat` or `wwq.sh`, two things happen automatically:

| Update type | What happens |
|---|---|
| **Official bank update** | Downloads the latest `questions.enc` from GitHub |
| **Code update** | Checks for a new app version and downloads changed Python files |

If you have a **custom bank active**, OTA updates the official backup in the background without touching your custom bank.

### Game Seeds & Bank Versions

Seeds now include the bank version: `A3F2C1@v2`

- Share this code with a friend to play the **exact same quiz**
- If their bank version differs, the game shows a warning: *"Questions may differ — run ./wwq to sync"*
- Old seeds (without `@v`) still work — no warning shown

### Creating a Custom Question Bank

Build your own themed bank with any model and topics and save it directly to the `banks/` registry:

```bash
python seed_bank.py                                     # Interactive wizard
python seed_bank.py --name cold_war --count 500 --topics "Cold War, Korean War"
python seed_bank.py --name custom_gpt --count 200 --model openai/gpt-4o  
```

- Custom banks are saved as `banks/<name>.enc` alongside an updated `banks/index.json`. 
- The minimum viable question count to generate a custom bank is **20**.
- If generation fails (bad API key, rate limit, etc.), partial runs are saved safely to `banks/questions_custom_raw.json` so you can resume later.

### Managing and Switching Banks

All banks (including the Official Bank) are tracked in `banks/index.json`.

In-game: **Settings → Manage Bank → Select Active Bank**
This will bring up a table of all available banks. Selecting one will immediately set it as the active bank for all future games.

Want to share a bank with a friend? 
1. Just send them your `banks/<name>.enc` file.
2. They can place it in their `banks/` folder.
3. Simply running `seed_bank.py` or editing `index.json` manually will register it!

To restore the official bank, simply select **Official WW1 & WW2 Bank** from the active bank menu. The official `questions.enc` is never overwritten securely updated via OTA on boot.

---

## Developer Guide: Question Bank Refresh

### Simulate Usage Data (recommended before refreshing)

Run the simulation agent to generate realistic question history without manual play:

```bash
# Simulate 50 sessions at intermediate skill level
python adversary/simulate_games.py --sessions 50 --skill intermediate

# Dry run — show what the history would look like without saving
python adversary/simulate_games.py --sessions 100 --skill random --dry-run
```

Skill profiles: `beginner`, `intermediate`, `expert`, `random`

### Partial Refresh (history-driven)

Retires the most over-used questions and replaces them with fresh ones:

```bash
python refresh_db.py --dry-run        # Preview what would be replaced
python refresh_db.py                  # Replace top 200 questions (≥3 asks)
python refresh_db.py --count 128 --threshold 5
```

Push the updated bank so all players receive it via OTA:
```bash
git add questions.enc version.txt
git commit -m "refresh: retire top-200 overused questions"
git push origin master
```

### Full Re-seed (from scratch)

```bash
python generate_db.py    # Generate questions_raw.json
python encrypt_db.py     # Wrap in version envelope and encrypt
# Update DATABASE_DECRYPTION_KEY in database.py with the printed key
```

---

## Troubleshooting

- **"Module Not Found":** Run the game through `wwq.bat` or `wwq.sh` — they handle the virtual environment automatically.
- **API Errors:** Check your internet connection and `.env` key. The game falls back to `local_bank` if an online connection fails.
- **OTA Update Fails:** Game continues with your last saved `questions.enc`. Try relaunching.
- **Custom bank seeding fails:** Your official bank is safe in `questions.enc.official`. Restore via Settings → Manage Bank.
- **Seed version mismatch warning:** Run `./wwq` to download the latest bank and re-launch.

## License & Contributing

This project is open-source. Feel free to submit Pull Requests to improve the historical accuracy of the question bank or to add new LLM providers!

---

