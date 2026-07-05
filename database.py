import sqlite3
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)
DB_NAME = "users.db"


@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone_number TEXT,
                roblox_nick TEXT DEFAULT '',
                is_attacked INTEGER DEFAULT 0,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                last_login INTEGER DEFAULT (strftime('%s', 'now')),
                is_active INTEGER DEFAULT 1
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_phone ON users(phone_number)")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auth_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                phone_number TEXT,
                status TEXT,
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)
        
        conn.commit()
        logger.info("Database initialized")


def add_user(user_id, username, first_name, last_name):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, first_name, last_name))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error adding user: {e}")
        return False


def save_phone_number(user_id, phone_number):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET phone_number = ?, last_login = strftime('%s', 'now') 
                WHERE user_id = ?
            """, (phone_number, user_id))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error saving phone: {e}")
        return False


def get_phone_number(user_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT phone_number FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting phone: {e}")
        return None


def save_roblox_nick(user_id, roblox_nick):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET roblox_nick = ? WHERE user_id = ?
            """, (roblox_nick, user_id))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error saving roblox nick: {e}")
        return False


def get_roblox_nick(user_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT roblox_nick FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting roblox nick: {e}")
        return None


def mark_attacked(user_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET is_attacked = 1 WHERE user_id = ?
            """, (user_id,))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error marking attacked: {e}")
        return False


def is_user_attacked(user_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_attacked FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] == 1 if result else False
    except Exception as e:
        logger.error(f"Error checking attacked: {e}")
        return False


def get_total_users():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Error getting total users: {e}")
        return 0


def update_last_login(user_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET last_login = strftime('%s', 'now') 
                WHERE user_id = ?
            """, (user_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Error updating last login: {e}")


def log_auth_attempt(user_id, phone_number, status):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO auth_logs (user_id, phone_number, status)
                VALUES (?, ?, ?)
            """, (user_id, phone_number, status))
            conn.commit()
    except Exception as e:
        logger.error(f"Error logging auth: {e}")


# Инициализируем БД
init_db()