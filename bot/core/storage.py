# core/storage.py
import json
import os
from pathlib import Path
import tempfile

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "users.json"
MAX_NOTE_LENGTH = 5000  # ограничение длины заметки (поменяй при необходимости)

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def load_data():
    ensure_data_dir()
    if not DATA_FILE.exists():
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        # если файл повреждён или недоступен — логируем и возвращаем пустую структуру
        print(f"[storage] load_data error: {e}")
        return {}

def save_data(data):
    ensure_data_dir()
    try:
        # атомарная запись: сначала в temp, затем replace
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(DATA_DIR)) as tf:
            json.dump(data, tf, ensure_ascii=False, indent=2)
            temp_name = tf.name
        os.replace(temp_name, DATA_FILE)
    except OSError as e:
        print(f"[storage] save_data error: {e}")

def add_note(user_id, note):
    if not note:
        return False
    if len(note) > MAX_NOTE_LENGTH:
        note = note[:MAX_NOTE_LENGTH]
    data = load_data()
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = {"notes": []}
    data[user_id]["notes"].append(note)
    save_data(data)
    return True

def get_notes(user_id):
    data = load_data()
    return data.get(str(user_id), {}).get("notes", [])

def reset_notes(user_id):
    data = load_data()
    user_id = str(user_id)
    if user_id in data:
        data[user_id]["notes"] = []
        save_data(data)
        return True
    return False
def search_notes(user_id, keyword):
    """
    Ищет заметки пользователя по ключевому слову (регистр игнорируется)
    """
    keyword = keyword.lower()
    notes = get_notes(user_id)
    return [note for note in notes if keyword in note.lower()]