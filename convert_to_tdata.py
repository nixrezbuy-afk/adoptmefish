import os
import json
import base64
from config import API_ID, API_HASH

SESSIONS_DIR = "sessions"
TDATA_DIR = "tdata"

os.makedirs(TDATA_DIR, exist_ok=True)

def convert_all_sessions():
    """Конвертирует все .session в .tdata"""
    sessions = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.session')]
    
    if not sessions:
        print("❌ Нет .session файлов!")
        return
    
    print(f"🔄 Конвертация {len(sessions)} сессий...")
    
    for session_file in sessions:
        try:
            session_path = os.path.join(SESSIONS_DIR, session_file)
            with open(session_path, 'r', encoding='utf-8') as f:
                session_string = f.read().strip()
            
            # Декодируем сессию
            session_bytes = base64.b64decode(session_string + '=' * (-len(session_string) % 4))
            
            # Создаем .tdata
            tdata = {
                'session': session_string,
                'api_id': API_ID,
                'api_hash': API_HASH,
                'version': 2,
                'auth_key': base64.b64encode(session_bytes).decode('utf-8')
            }
            
            user_id = session_file.replace('.session', '')
            tdata_path = os.path.join(TDATA_DIR, f"{user_id}.tdata")
            
            with open(tdata_path, 'w', encoding='utf-8') as f:
                json.dump(tdata, f, indent=2)
            
            print(f"✅ {session_file} → {user_id}.tdata")
            
        except Exception as e:
            print(f"❌ Ошибка {session_file}: {e}")
    
    print(f"\n✅ Все сессии сконвертированы в {TDATA_DIR}/")
    print("\n📁 Использование .tdata:")
    print("  Windows: C:\\Users\\%USERNAME%\\AppData\\Roaming\\Telegram Desktop\\tdata\\")
    print("  Linux: ~/.local/share/TelegramDesktop/tdata/")
    print("  macOS: ~/Library/Application Support/Telegram Desktop/tdata/")

if __name__ == "__main__":
    convert_all_sessions()