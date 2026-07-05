import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import TOKEN
from handlers import router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Подключаем роутер с хендлерами
dp.include_router(router)


async def main():
    logger.info("🚀 Бот запущен!")
    
    try:
        me = await bot.get_me()
        logger.info(f"✅ Бот: @{me.username} (ID: {me.id})")
        logger.info(f"🔗 Ссылка: https://t.me/{me.username}")
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о боте: {e}")
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"❌ Ошибка поллинга: {e}")
    finally:
        await bot.close()
        logger.info("🛑 Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💀 Критическая ошибка: {e}")