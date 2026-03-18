import os
import sys
import json
import random
import hashlib
import ollama
from dotenv import load_dotenv, set_key
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from state import GameState, QuizConfig, generate_seed, decode_seed, DEFAULT_TOPIC
from agents import generate_question, validate_question
import question_history as qh
from question_history import get_weights_for_candidates

try:
    from litellm.types.utils import ModelResponse
except ImportError:
    ModelResponse = type('ModelResponse', (object,), {})

from database import active_bank, get_active_bank_info

load_dotenv()
console = Console()

def print_header():
    console.print(Panel.fit("[bold yellow]WW1 & WW2 Agentic Trivia[/bold yellow]\n[italic]A Dynamic Historical Quiz[/italic]", border_style="yellow"))

def bank_management_menu():
    """Settings sub-menu for managing the question bank."""
    from database import active_bank, get_active_bank_info, INDEX_PATH, BANKS_DIR
    import shutil, urllib.request

    OFFICIAL_BACKUP = "questions.enc.official"
    DB_PATH = "questions.enc"
    OTA_URL = "https://raw.githubusercontent.com/adityasricharan/wwq/master/questions.enc"

    while True:
        info = get_active_bank_info()
        bank_label = f"[green]{info['name']}[/green]" if info.get("is_official") else f"[yellow]{info['name']}[/yellow]"
        bv = active_bank.bank_version
        qcount = len(active_bank._questions)

        console.print(f"\n[bold yellow]--- Bank Management ---[/bold yellow]")
        console.print(f"  Active: {bank_label}  |  Bank v{bv}  |  {qcount} questions")
        console.print("1. Select Active Bank")
        console.print("2. Restore Official Bank (from local backup)")
        console.print("3. Re-download Official Bank from GitHub")
        console.print("4. View Bank Statistics")
        console.print("5. Back")

        sub = Prompt.ask("Select", choices=["1", "2", "3", "4", "5"])

        if sub == "1":
            try:
                with open(INDEX_PATH, "r") as f:
                    index_data = json.load(f)
                banks = index_data.get("banks", [])
                
                console.print("\n[bold cyan]Available Banks:[/bold cyan]")
                for i, b in enumerate(banks):
                    active_marker = " * " if b["id"] == info["id"] else "   "
                    color = "green" if b.get("is_official") else "yellow"
                    console.print(f"{active_marker}{i+1}. [{color}]{b['name']}[/{color}] ({b.get('path', '')})")
                
                choice_str = Prompt.ask("\nEnter number to select (or press Enter to cancel)", default="")
                if choice_str.isdigit():
                    idx = int(choice_str) - 1
                    if 0 <= idx < len(banks):
                        selected = banks[idx]
                        index_data["active_bank_id"] = selected["id"]
                        with open(INDEX_PATH, "w") as f:
                            json.dump(index_data, f, indent=2)
                        console.print(f"[green]✅ Switched active bank to: {selected['name']}. Relaunch the game to apply.[/green]")
                        # We don't hot-reload here because GameState depends on active_bank.
            except Exception as e:
                console.print(f"[red]Error loading bank index: {e}[/red]")

        elif sub == "2":
            if not os.path.exists(OFFICIAL_BACKUP):
                console.print("[yellow]No local backup found (questions.enc.official). Use option 3 to re-download.[/yellow]")
            else:
                shutil.copy2(OFFICIAL_BACKUP, DB_PATH)
                console.print("[green]✅ Official bank restored to questions.enc. Make sure it's selected as Active.[/green]")
                console.print("[dim]Backup file kept.[/dim]")

        elif sub == "3":
            console.print("[cyan]Downloading official bank from GitHub...[/cyan]")
            try:
                tmp = DB_PATH + ".ota.tmp"
                urllib.request.urlretrieve(OTA_URL, tmp)
                shutil.move(tmp, DB_PATH)
                console.print("[green]✅ Official bank re-downloaded to questions.enc.[/green]")
            except Exception as e:
                console.print(f"[red]Download failed: {e}[/red]")

        elif sub == "4":
            from collections import Counter
            diff_counts = Counter(q.difficulty for q in active_bank._questions)
            console.print("\n[bold]Bank Statistics[/bold]")
            for d in sorted(diff_counts):
                console.print(f"  Difficulty {d}: {diff_counts[d]} questions")
            import question_history as qh
            h = qh.load_history()
            console.print(f"  Sessions tracked: {h.get('total_sessions', 0)}")
            console.print(f"  Questions in history: {len(h.get('entries', {}))}")

        elif sub == "5":
            break


def settings_menu(state: GameState):
    while True:
        console.print("\n[bold yellow]--- Settings ---[/bold yellow]")
        console.print(f"1. Change LLM Provider (Current: {state.config.llm_provider} / {state.config.llm_model})")
        console.print(f"2. Change Topic (Current: {state.config.topic})")
        console.print(f"3. Override Difficulty (Current: {state.override_difficulty if state.override_difficulty else 'Auto'})")
        console.print("4. Set API Key")
        console.print("5. Manage Question Bank")
        console.print("6. Return to Game")

        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "5", "6"])
        if choice == "1":
            provider = Prompt.ask("Choose provider", choices=["local_bank", "gemini", "ollama", "openai"])
            state.config.llm_provider = provider
            if provider == "local_bank":
                state.config.llm_model = "questions.enc"
                console.print("[green]Switched to curated offline knowledge bank.[/green]")
            elif provider == "gemini":
                state.config.llm_model = "gemini-2.5-flash"
            elif provider == "ollama":
                try:
                    models_res = ollama.list()
                    models_list = models_res.get("models", []) if isinstance(models_res, dict) else getattr(models_res, "models", [])
                    available_models = []
                    for m in models_list:
                        name = m.get("model", m.get("name")) if isinstance(m, dict) else getattr(m, "model", getattr(m, "name", str(m)))
                        if name: available_models.append(name)

                    if available_models:
                        console.print("\n[bold green]Available Local Ollama Models:[/bold green]")
                        for m in available_models:
                            console.print(f"  - {m}")
                    else:
                        console.print("\n[yellow]No Ollama models downloaded yet.[/yellow]")
                except Exception as e:
                    console.print(f"\n[yellow]Could not fetch local models. Ensure Ollama is installed and running. ({e})[/yellow]")

                model_choice = Prompt.ask("\nEnter Ollama model name", default="qwen2.5:0.5b")
                try:
                    with console.status(f"[bold cyan]Fetching and verifying model '{model_choice}'...[/bold cyan]"):
                        ollama.pull(model_choice)
                    state.config.llm_model = model_choice
                    console.print(f"[green]Successfully configured and verified: {model_choice}[/green]")
                except Exception as e:
                    console.print(f"\n[bold red]Failed to pull {model_choice}. Please verify the model name and your internet connection. ({e})[/bold red]")
                    console.print(f"[yellow]Reverting to previous model: {state.config.llm_model}[/yellow]")
            elif provider == "openai":
                state.config.llm_model = Prompt.ask("Enter OpenAI model name", default="gpt-4o-mini")
        elif choice == "2":
            topic = Prompt.ask("Enter new topic", default="")
            if topic:
                state.config.topic = topic
        elif choice == "3":
            diff = Prompt.ask("Enter specific difficulty (1-5) or 'auto' to reset", default="auto")
            if diff.lower() == "auto":
                state.override_difficulty = None
            elif diff.isdigit() and 1 <= int(diff) <= 5:
                state.override_difficulty = int(diff)
        elif choice == "4":
            if state.config.llm_provider == "openai":
                os.environ["OPENAI_API_KEY"] = Prompt.ask("Enter OpenAI API Key")
            else:
                key = Prompt.ask("Enter Google API Key")
                os.environ["GOOGLE_API_KEY"] = key
                set_key(".env", "GOOGLE_API_KEY", key)
        elif choice == "5":
            bank_management_menu()
        elif choice == "6":
            break

def draw_vs_questions(bank, seed_str: str, count: int) -> list[str]:
    """Deterministically draws `count` question texts using the given seed.
    Uses an isolated RNG so external random calls don't break determinism.
    Strictly enforces that no two questions share the same answer.
    """
    from database import normalize_answer
    
    # Convert string seed to integer for random.Random
    seed_int = int(hashlib.sha256(seed_str.encode('utf-8')).hexdigest()[:8], 16)
    rng = random.Random(seed_int)
    
    candidates = bank._questions[:]
    rng.shuffle(candidates)
    
    drawn_texts = []
    seen_answers = set()
    
    for q in candidates:
        ans = normalize_answer(q.correct_answer)
        if ans not in seen_answers:
            drawn_texts.append(q.question_text)
            seen_answers.add(ans)
            if len(drawn_texts) == count:
                break
                
    return drawn_texts


def setup_game() -> GameState:
    print_header()
    from database import active_bank
    import hashlib

    # 1. Mode Selection
    console.print("\n[bold cyan]Select Game Mode:[/bold cyan]")
    console.print("1. [bold]Adaptive Mode[/bold] (Default, difficulty scales dynamically)")
    console.print("2. [bold]VS Mode[/bold]       (Deterministic fixed questions — share seed to compete)")
    
    mode_choice = Prompt.ask("Mode", choices=["1", "2"], default="1")
    game_mode = "adaptive" if mode_choice == "1" else "vs"

    # 2. Quiz Length
    q_count_str = Prompt.ask("\nHow many questions?", default="20")
    try:
        total_questions = int(q_count_str)
        total_questions = max(5, min(total_questions, len(active_bank._questions)))
    except ValueError:
        total_questions = 20

    config = QuizConfig()
    seed_hash = ""
    vs_question_list = []

    # 3. Mode-Specific Setup
    if game_mode == "adaptive":
        topic = Prompt.ask("\nTopic focus? (e.g., 'Spies', 'Naval Battles') [Leave blank for General]", default=DEFAULT_TOPIC)
        config.topic = topic
        # Generate an internal hidden seed solely for reproducibility of the adaptive path
        seed_hash = generate_seed(topic, bank_version=active_bank.bank_version)
        console.print(f"\n[green]Starting Adaptive Quiz[/green] ({total_questions} questions)")

    else:
        # VS MODE
        use_existing = Confirm.ask("\nDo you have a seed code to join a VS match?", default=False)
        if use_existing:
            seed_hash = Prompt.ask("Enter VS seed")
            # If user forgot the VS: prefix, we'll let decode_seed handle or reject it
            if not seed_hash.upper().startswith("VS:"):
                seed_hash = "VS:" + seed_hash

            _, topic, seed_bank_version = decode_seed(seed_hash)
            config.topic = topic
            console.print(f"\n[bold green]Loaded VS Seed:[/bold green] {seed_hash}")
            console.print(f"[bold green]Topic:[/bold green] {topic}")
            
            if seed_bank_version is not None and active_bank.bank_version != seed_bank_version:
                console.print(f"\n[yellow]⚠️  Bank version mismatch: seed was created on Bank v{seed_bank_version}, "
                              f"but your bank is v{active_bank.bank_version}.[/yellow]")
                console.print("[dim]   Questions may differ from the original match. Run ./wwq to sync.[/dim]")
        else:
            topic = Prompt.ask("\nTopic focus? [Leave blank for General]", default=DEFAULT_TOPIC)
            config.topic = topic
            seed_hash = generate_seed(topic, bank_version=active_bank.bank_version)
            console.print(f"\n[bold green]🆚 VS MODE SEED (Share to challenge friends!):[/bold green] [bold white]{seed_hash}[/bold white]")

        # Draw the deterministic question list upfront
        vs_question_list = draw_vs_questions(active_bank, seed_hash, total_questions)

    state = GameState(
        seed=seed_hash, 
        config=config,
        game_mode=game_mode,
        total_questions=total_questions,
        vs_question_list=vs_question_list
    )

    if not os.environ.get("GOOGLE_API_KEY") and state.config.llm_provider == "gemini":
        console.print("\n[yellow]Google Gemini requires an API key.[/yellow]")
        key = Prompt.ask("Please paste your free Google Gemini API Key (or press Enter to skip and set it later in Settings)").strip()
        if key:
            os.environ["GOOGLE_API_KEY"] = key
            set_key(".env", "GOOGLE_API_KEY", key)

    return state

def play_round(state: GameState, history: dict):
    diff_to_use = state.override_difficulty if state.override_difficulty is not None else state.current_difficulty
    console.print(f"\n[bold blue]--- Question {state.questions_answered + 1} (Difficulty: {diff_to_use}) ---[/bold blue]")
    
    question = None
    
    # In VS Mode, we already have the exact questions lined up deterministically.
    if state.game_mode == "vs":
        from database import active_bank
        q_text = state.vs_question_list[state.questions_answered]
        
        # We need the full Question object from the bank
        for bank_q in active_bank._questions:
            if bank_q.question_text == q_text:
                question = bank_q
                break
                
        if not question:
            console.print("[red]Critical Error: VS Mode question not found in active bank.[/red]")
            sys.exit(1)
            
        with console.status("[bold cyan]Loading next VS Match question...[/bold cyan]") as status:
            import time; time.sleep(0.5) # Slight UX pause
            
    else:
        # Adaptive Mode - use LLM agent and difficulty scaling
        api_error_count = 0
        with console.status(f"[bold cyan]The Historian ({state.config.llm_model}) is researching a question...[/bold cyan]") as status:
            model_seed = random.randint(1, 100000)
            
            valid = False
            attempts = 0
            
        while not valid and attempts < 3:
            try:
                question = generate_question(state.config.llm_provider, state.config.llm_model, state.config.topic, state.config.format, diff_to_use, model_seed, state.seen_questions, state.seen_answers, history)
                status.update("[bold cyan]The Fact Checker is reviewing the question...[/bold cyan]")
                
                validation = validate_question(state.config.llm_provider, state.config.llm_model, question)
                if validation.is_valid:
                    valid = True
                else:
                    attempts = attempts + 1
                    model_seed = model_seed + 1
                api_error_count = 0
            except Exception as e:
                status.stop()
                api_error_count += 1
                error_str = str(e)
                if state.config.llm_provider == "local_bank":
                    console.print(f"\n[yellow]Local Database Exception: {e}[/yellow]")
                    console.print("[yellow]The local bank might be exhausted for this specific topic/difficulty. Try changing settings.[/yellow]")
                    return
                else:
                    console.print(f"\n[red]API Error Encountered: {e}[/red]")
                
                if api_error_count >= 2:
                    if Confirm.ask("[bold red]Multiple API errors detected. Would you like to exit?[/bold red]", default=False):
                        sys.exit(1)
                    api_error_count = 0
                    
                if state.config.llm_provider == "ollama":
                    console.print("[yellow]Ollama encountered an error. Ensure Ollama is running and the model is pulled.[/yellow]")
                    new_key = Prompt.ask("Press Enter to retry, or type 'exit' to quit").strip()
                elif "503 UNAVAILABLE" in error_str:
                    console.print("[yellow]The Google Gemini API is currently experiencing high demand and is temporarily unavailable.[/yellow]")
                    new_key = Prompt.ask("Press Enter to retry, or type 'exit' to quit").strip()
                elif "429 RESOURCE_EXHAUSTED" in error_str:
                    console.print("[yellow]Your Google project has exceeded its quota or spending cap, or you are being rate-limited.[/yellow]")
                    new_key = Prompt.ask("Please paste a different Google API Key (or press Enter to retry, or type 'exit' to quit)").strip()
                else:
                    console.print(f"[yellow]This is often caused by an invalid/expired API Key for {state.config.llm_provider}.[/yellow]")
                    new_key = Prompt.ask("Please paste a valid API Key (or press Enter to retry, or type 'exit' to quit)").strip()

                if 'new_key' in locals() and new_key.lower() == 'exit':
                    sys.exit(1)
                elif 'new_key' in locals() and new_key:
                    if state.config.llm_provider == "openai":
                        os.environ["OPENAI_API_KEY"] = new_key
                    else:
                        os.environ["GOOGLE_API_KEY"] = new_key
                        set_key(".env", "GOOGLE_API_KEY", new_key)
                    console.print("[green]API Key updated. Retrying...[/green]")
                status.start()
                
        if not valid or question is None:
            console.print("[red]The Historian struggled to find an accurate question. Let's try an easier one next time.[/red]")
            state.current_difficulty = max(1, state.current_difficulty - 1)
            return

    while True:
        options = question.options.copy()
        # Randomize the option order completely
        random.shuffle(options)
        
        console.print(f"\n[bold white]{question.question_text}[/bold white]\n")
        
        for i, opt in enumerate(options):
            console.print(f"{i + 1}. {opt}")
            
        choice_idx = Prompt.ask("\nYour Answer (1-4), 's' for settings, or 'exit'", choices=["1", "2", "3", "4", "settings", "s", "exit"], default="")
        
        if choice_idx == "exit":
            sys.exit(0)
        elif choice_idx in ["settings", "s"]:
            settings_menu(state)
            console.print("\n[cyan]Resuming current question with new settings...[/cyan]")
            continue
        elif choice_idx in ["1", "2", "3", "4"]:
            break
        else:
            continue
        
    chosen_answer = options[int(choice_idx) - 1]
    
    state.seen_questions.add(question.question_text)
    
    from database import normalize_answer
    state.seen_answers.add(normalize_answer(question.correct_answer))
    
    qh.record_asked(history, question.question_text)
    
    earned = 0
    if chosen_answer == question.correct_answer:
        console.print("\n[bold green]Correct![/bold green]")
        console.print(f"[italic]{question.explanation}[/italic]")
        earned = 10 * diff_to_use
        state.score += earned
        state.current_difficulty = min(state.config.max_difficulty, state.current_difficulty + 1)
    else:
        console.print(f"\n[bold red]Incorrect![/bold red] The correct answer was: {question.correct_answer}")
        console.print(f"[italic]{question.explanation}[/italic]")
        penalty = 5 / diff_to_use
        earned = -penalty
        state.score += earned
        state.current_difficulty = max(1, state.current_difficulty - 1)
        
    state.question_history.append({
        "question": question.question_text,
        "given": chosen_answer,
        "correct": question.correct_answer,
        "diff": diff_to_use,
        "score": earned
    })
        
    state.questions_answered += 1
    random.seed(model_seed + state.questions_answered)
    
    console.print(f"[bold]Current Score: {state.score:.1f}[/bold]")

from rich.table import Table

def display_review(state: GameState):
    if not state.question_history:
        return
        
    console.print("\n[bold magenta]=== End of Game Review ===[/bold magenta]")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Q#", style="dim", width=4)
    table.add_column("Question")
    table.add_column("Your Answer")
    table.add_column("Correct Answer")
    table.add_column("Diff", justify="center")
    table.add_column("Points", justify="right")
    
    total_max_possible = 0
    total_earned = 0
    
    for idx, hist in enumerate(state.question_history):
        q_num = str(idx + 1)
        q_text = hist["question"]
        earned = hist["score"]
        diff = hist["diff"]
        
        total_max_possible += (10 * diff)
        
        is_correct = earned > 0
        given_style = "[green]" if is_correct else "[red]"
        given = f"{given_style}{hist['given']}[/{given_style.strip('[]')}]"
        correct = hist["correct"]
        points = f"[green]+{earned:.1f}[/green]" if earned > 0 else f"[red]{earned:.1f}[/red]"
        total_earned += earned
        
        table.add_row(q_num, q_text, given, correct, str(diff), points)
        
    console.print(table)
    
    # 1-10 Knowledge Scale
    # If they get everything perfectly, score aligns closely with max possible.
    # 1-10 Knowledge Scale
    # If they get everything perfectly, score aligns closely with max possible.
    if total_max_possible > 0:
        ratio = max(0.0, float(total_earned) / float(total_max_possible))
        scale = min(10, max(1, round(ratio * 10)))
    else:
        scale = 1
        
    console.print(f"\n[bold]Final Score: {state.score:.1f}[/bold] (Questions answered: {state.questions_answered})")
    console.print(f"[bold gold1]Your Historical Knowledge Scale: {scale} / 10[/bold gold1]")

def main():
    # Load global question history for weighted sampling
    history = qh.load_history()
    qh.start_new_session(history)

    state = setup_game()

    while True:
        if state.questions_answered >= state.total_questions:
            console.print(f"\n[bold yellow]Quiz complete! You answered all {state.total_questions} questions.[/bold yellow]")
            break

        play_round(state, history)
        choice = Prompt.ask("\n[bold yellow]Continue to next question?[/bold yellow] (y/n/s for settings/exit to quit)", choices=["y", "n", "s", "exit"], default="y")

        if choice == "exit":
            break

        while choice == "s":
            settings_menu(state)
            choice = Prompt.ask("\n[bold yellow]Continue to next question?[/bold yellow] (y/n/s for settings/exit to quit)", choices=["y", "n", "s", "exit"], default="y")
            if choice == "exit":
                break

        if choice == "n" or choice == "exit":
            break

    display_review(state)
    qh.save_history(history)
    
    if state.game_mode == "vs":
        console.print(f"\n[bold cyan]VS Mode Seed: {state.seed}[/bold cyan]")
        console.print("[dim]Share this seed with friends to replay this exact quiz against them![/dim]")
    
    console.print("\n[green]Thanks for playing![/green]")


if __name__ == "__main__":
    main()
