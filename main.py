import os
import sys
import random
import ollama
from dotenv import load_dotenv, set_key
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from state import GameState, QuizConfig, generate_seed, decode_seed
from agents import generate_question, validate_question
import question_history as qh

load_dotenv()
console = Console()

def print_header():
    console.print(Panel.fit("[bold yellow]WW1 & WW2 Agentic Trivia[/bold yellow]\n[italic]A Dynamic Historical Quiz[/italic]", border_style="yellow"))

def bank_management_menu():
    """Settings sub-menu for managing the question bank."""
    from database import active_bank
    import shutil, urllib.request

    OFFICIAL_BACKUP = "questions.enc.official"
    DB_PATH = "questions.enc"
    OTA_URL = "https://raw.githubusercontent.com/adityasricharan/wwq/master/questions.enc"

    bank_label = "[yellow]Custom[/yellow]" if os.path.exists(OFFICIAL_BACKUP) else "[green]Official[/green]"
    bv = active_bank.bank_version
    qcount = len(active_bank._questions)

    while True:
        console.print(f"\n[bold yellow]--- Bank Management ---[/bold yellow]")
        console.print(f"  Active: {bank_label}  |  Bank v{bv}  |  {qcount} questions")
        console.print("1. Restore Official Bank (from local backup)")
        console.print("2. Re-download Official Bank from GitHub")
        console.print("3. View Bank Statistics")
        console.print("4. Back")

        sub = Prompt.ask("Select", choices=["1", "2", "3", "4"])

        if sub == "1":
            if not os.path.exists(OFFICIAL_BACKUP):
                console.print("[yellow]No local backup found (questions.enc.official). Use option 2 to re-download.[/yellow]")
            else:
                shutil.copy2(OFFICIAL_BACKUP, DB_PATH)
                console.print("[green]✅ Official bank restored from local backup. Relaunch the game to apply.[/green]")
                if os.path.exists(OFFICIAL_BACKUP):
                    os.remove(OFFICIAL_BACKUP)
                    console.print("[dim]Backup file removed (you are now on the official bank).[/dim]")

        elif sub == "2":
            console.print("[cyan]Downloading official bank from GitHub...[/cyan]")
            try:
                tmp = DB_PATH + ".ota.tmp"
                urllib.request.urlretrieve(OTA_URL, tmp)
                # If user has a custom bank, update the official backup
                if os.path.exists(OFFICIAL_BACKUP):
                    shutil.move(tmp, OFFICIAL_BACKUP)
                    console.print("[green]✅ Official backup updated from GitHub. Your custom bank is unchanged.[/green]")
                else:
                    shutil.move(tmp, DB_PATH)
                    console.print("[green]✅ Official bank re-downloaded. Relaunch to apply.[/green]")
            except Exception as e:
                console.print(f"[red]Download failed: {e}[/red]")

        elif sub == "3":
            from collections import Counter
            diff_counts = Counter(q.difficulty for q in active_bank._questions)
            console.print("\n[bold]Bank Statistics[/bold]")
            for d in sorted(diff_counts):
                console.print(f"  Difficulty {d}: {diff_counts[d]} questions")
            import question_history as qh
            h = qh.load_history()
            console.print(f"  Sessions tracked: {h.get('total_sessions', 0)}")
            console.print(f"  Questions in history: {len(h.get('entries', {}))}")

        elif sub == "4":
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

def setup_game() -> GameState:
    print_header()
    from database import active_bank

    use_custom_seed = Confirm.ask("Do you have a deterministic hashcode/seed you want to play with?", default=False)
    if use_custom_seed:
        seed_hash = Prompt.ask("Enter seed")
        seed, topic, seed_bank_version = decode_seed(seed_hash)
        config = QuizConfig(topic=topic)
        console.print(f"\n[bold green]Loaded Game Seed:[/bold green] {seed_hash}")
        console.print(f"[bold green]Topic:[/bold green] {topic}")
        # Warn if bank versions differ
        if seed_bank_version is not None and active_bank.bank_version != seed_bank_version:
            console.print(f"\n[yellow]⚠️  Bank version mismatch: seed was created on Bank v{seed_bank_version}, "
                          f"but your bank is v{active_bank.bank_version}.[/yellow]")
            console.print("[dim]   Questions may differ from the original session. "
                          "Run ./wwq to check for bank updates.[/dim]")
    else:
        topic = Prompt.ask("Any specific topic or focus? (e.g., 'Spies', 'Weapons', 'Naval Battles') [Leave blank for General]", default="General WW1 and WW2 History")
        seed_hash = generate_seed(topic, bank_version=active_bank.bank_version)
        seed, _, _ = decode_seed(seed_hash)
        config = QuizConfig(topic=topic)
        console.print(f"\n[bold green]Game Seed (Share this short code with friends!):[/bold green] [bold white]{seed_hash}[/bold white]")

    random.seed(seed)

    state = GameState(seed=seed_hash, config=config)

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
    
    api_error_count = 0
    with console.status(f"[bold cyan]The Historian ({state.config.llm_model}) is researching a question...[/bold cyan]") as status:
        model_seed = random.randint(1, 100000)
        
        valid = False
        attempts = 0
        question = None
        
        while not valid and attempts < 3:
            try:
                question = generate_question(state.config.llm_provider, state.config.llm_model, state.config.topic, state.config.format, diff_to_use, model_seed, state.seen_questions, history=history)
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
    if total_max_possible > 0:
        ratio = max(0, total_earned / total_max_possible)
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
        if state.questions_answered >= 20:
            console.print("\n[bold yellow]You have reached the maximum length of 20 questions for this session![/bold yellow]")
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
    console.print(f"\n[bold cyan]Game Seed: {state.seed}[/bold cyan]")
    if ":" in state.seed:
        short, topic = state.seed.split(":", 1)
        console.print(f"[dim]Share the code [bold]{short}[/bold] + the topic '[italic]{topic}[/italic]' with friends to replay this exact quiz![/dim]")
    else:
        console.print(f"[dim]Share the code [bold]{state.seed}[/bold] with friends to replay this exact quiz![/dim]")
    console.print("[green]Thanks for playing![/green]")


if __name__ == "__main__":
    main()
