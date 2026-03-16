import os
import json
from cryptography.fernet import Fernet

def main():
    if not os.path.exists("questions_raw.json"):
        print("questions_raw.json not found. Run generate_db.py first.")
        return
        
    # Generate a new encryption key
    key = Fernet.generate_key()
    cipher = Fernet(key)
    
    with open("questions_raw.json", "r", encoding="utf-8") as f:
        data = f.read()
        
    encrypted_data = cipher.encrypt(data.encode('utf-8'))
    
    with open("questions.enc", "wb") as f:
        f.write(encrypted_data)
        
    print("Database successfully encrypted into 'questions.enc'.")
    print("\n" + "="*50)
    print("CRITICAL: KEEP THIS KEY SAFE. BAKE IT INTO STATE.PY:")
    print(f"DATABASE_DECRYPTION_KEY = b'{key.decode('utf-8')}'")
    print("="*50 + "\n")
    
    # We delete the raw JSON so users don't get it by accident in the repo
    # os.remove("questions_raw.json") # Uncomment in prod to auto-hide plain text
    print("Note: questions_raw.json was left on disk for debugging. Delete before shipping.")

if __name__ == "__main__":
    main()
