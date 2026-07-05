import asyncio
import os
import logging
import time
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH, SPAM_TEXT

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SESSIONS_DIR = "sessions"
INTERVAL = 45  # секунд


class SpamBot:
    def __init__(self, session_file: str):
        self.session_file = session_file
        self.user_id = os.path.basename(session_file).replace('.session', '')
        self.client = None
        self.running = True

    async def connect(self):
        """Подключение к аккаунту"""
        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                session_string = f.read().strip()

            self.client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
            await self.client.connect()

            if not await self.client.is_user_authorized():
                logger.error(f"❌ Сессия {self.user_id} не активна")
                return False

            me = await self.client.get_me()
            logger.info(f"✅ Подключен: @{me.username} (ID: {me.id})")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка подключения {self.user_id}: {e}")
            return False

    async def get_all_groups(self):
        """Получить все группы и каналы"""
        groups = []
        try:
            dialogs = await self.client.get_dialogs()
            for dialog in dialogs:
                # Группы, супергруппы, каналы
                if dialog.is_group or dialog.is_channel:
                    groups.append({
                        'id': dialog.id,
                        'name': dialog.name,
                        'entity': dialog.entity,
                        'type': 'group' if dialog.is_group else 'channel'
                    })
            logger.info(f"📋 Найдено {len(groups)} групп/каналов для {self.user_id}")
            return groups
        except Exception as e:
            logger.error(f"❌ Ошибка получения диалогов {self.user_id}: {e}")
            return []

    async def send_spam_to_group(self, group, attempt=0):
        """Отправить спам в группу"""
        try:
            await self.client.send_message(group['entity'], SPAM_TEXT)
            logger.info(f"✅ [{self.user_id}] Спам в {group['name']} (ID: {group['id']})")
            return True
        except Exception as e:
            if "FLOOD" in str(e) or "Too many requests" in str(e):
                logger.warning(f"⚠️ [{self.user_id}] Флуд-лимит в {group['name']}, пауза 60с")
                await asyncio.sleep(60)
                if attempt < 3:
                    return await self.send_spam_to_group(group, attempt + 1)
            else:
                logger.error(f"❌ [{self.user_id}] Ошибка в {group['name']}: {e}")
            return False

    async def spam_loop(self):
        """Бесконечный цикл рассылки"""
        if not await self.connect():
            return

        groups = await self.get_all_groups()
        if not groups:
            logger.warning(f"⚠️ Нет групп для {self.user_id}")
            await self.client.disconnect()
            return

        logger.info(f"🔄 Запуск бесконечной рассылки для {self.user_id} (интервал {INTERVAL}с)")

        while self.running:
            try:
                for group in groups:
                    if not self.running:
                        break

                    logger.info(f"📤 [{self.user_id}] Отправка в {group['name']}...")
                    success = await self.send_spam_to_group(group)

                    if success:
                        logger.info(f"✅ [{self.user_id}] Отправлено в {group['name']}")

                    # Пауза между группами 3-7 секунд (имитация человека)
                    await asyncio.sleep(3 + (hash(group['name']) % 5))

                if self.running:
                    logger.info(f"⏳ [{self.user_id}] Цикл завершен, следующая волна через {INTERVAL}с")
                    await asyncio.sleep(INTERVAL)

            except Exception as e:
                logger.error(f"❌ [{self.user_id}] Ошибка в цикле: {e}")
                await asyncio.sleep(30)

        await self.client.disconnect()
        logger.info(f"🛑 [{self.user_id}] Остановлен")

    def stop(self):
        self.running = False


async def main():
    """Запуск всех аккаунтов"""
    sessions = []
    for file in os.listdir(SESSIONS_DIR):
        if file.endswith(".session"):
            sessions.append(os.path.join(SESSIONS_DIR, file))

    if not sessions:
        logger.error("❌ Нет .session файлов в папке sessions!")
        return

    logger.info(f"🚀 Найдено {len(sessions)} сессий")

    # Создаем задачи для каждого аккаунта
    bots = []
    tasks = []

    for session_file in sessions:
        bot = SpamBot(session_file)
        bots.append(bot)
        tasks.append(asyncio.create_task(bot.spam_loop()))
        await asyncio.sleep(2)  # Задержка между запусками аккаунтов

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("🛑 Остановка по Ctrl+C")
        for bot in bots:
            bot.stop()
    finally:
        for bot in bots:
            await bot.client.disconnect() if bot.client else None


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Завершено")