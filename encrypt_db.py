import os
import json
import re
from cryptography.fernet import Fernet

def bump_bank_version(version_path: str = "version.py") -> int:
    """Reads BANK_VERSION from version.py, increments it, writes it back, returns new value."""
    if not os.path.exists(version_path):
        return 1
    with open(version_path, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"BANK_VERSION\s*=\s*(\d+)", content)
    current = int(match.group(1)) if match else 0
    new_version = current + 1
    new_content = re.sub(r"BANK_VERSION\s*=\s*\d+", f"BANK_VERSION = {new_version}", content)
    with open(version_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return new_version


def main():
    if not os.path.exists("questions_raw.json"):
        print("questions_raw.json not found. Run generate_db.py first.")
        return

    # Bump the bank version before encrypting
    bank_version = bump_bank_version()
    print(f"Bank version: v{bank_version}")

    # Generate a new encryption key
    key = Fernet.generate_key()
    cipher = Fernet(key)

    with open("questions_raw.json", "r", encoding="utf-8") as f:
        questions = json.load(f)

    # Wrap in version envelope: {"bank_version": N, "questions": [...]}
    envelope = {"bank_version": bank_version, "questions": questions}
    data = json.dumps(envelope)

    encrypted_data = cipher.encrypt(data.encode("utf-8"))

    with open("questions.enc", "wb") as f:
        f.write(encrypted_data)

    print("Database successfully encrypted into 'questions.enc'.")
    print("\n" + "="*50)
    print("CRITICAL: KEEP THIS KEY SAFE. BAKE IT INTO DATABASE.PY:")
    print(f"DATABASE_DECRYPTION_KEY = b'{key.decode('utf-8')}'")
    print("="*50 + "\n")
    print("Note: questions_raw.json was left on disk for debugging. Delete before shipping.")

if __name__ == "__main__":
    main()
