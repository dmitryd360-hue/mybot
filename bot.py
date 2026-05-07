import asyncio
import logging
from datetime import datetime, date
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    LabeledPrice, PreCheckoutQuery, Message
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import sqlite3

# ---------- НАСТРОЙКИ ----------
BOT_TOKEN = "8520742550:AAE-8fxrY7Fr6o2xSv18GCSMtk_2aQviCGs"  # ⚠️ Замени на свой токен
ADMIN_ID = 7762090976  # ⚠️ Замени на свой Telegram ID
PRIVATE_CHANNEL_LINK = "https://t.me/+ukyC6cdndyhkZjIy"  # ⚠️ Замени
ADMIN_USERNAME = "@sander_stark"
BOT_USERNAME = "sanderstark_bot"  # ⚠️ Замени на username бота
PRICE_STARS_PROJECT = 50
PRICE_STARS_5_REFS = 15
PRICE_STARS_10_REFS = 30
REFERRAL_COST = 10

# ---------- БАЗА ДАННЫХ ----------
conn = sqlite3.connect("sander_stark.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    referrer_id INTEGER,
    referrals_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'Пользователь',
    balance_ref REAL DEFAULT 0,
    last_self_ref_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER,
    referred_id INTEGER,
    date TEXT,
    is_self_ref INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    project_name TEXT,
    payment_method TEXT,
    payment_status TEXT DEFAULT 'ожидает',
    admin_approved INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_stats (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    total_uses INTEGER DEFAULT 0,
    orders_completed INTEGER DEFAULT 0,
    orders_pending INTEGER DEFAULT 0
)
""")
cursor.execute("INSERT OR IGNORE INTO bot_stats (id) VALUES (1)")
conn.commit()

# ---------- ЛОГИРОВАНИЕ ----------
logging.basicConfig(level=logging.INFO)

# ---------- БОТ И ДИСПЕТЧЕР ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ---------- СОСТОЯНИЯ FSM ----------
class ProjectCreation(StatesGroup):
    choosing_payment = State()
    entering_name = State()
    confirm_payment = State()

class AdminGiveRef(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()

class ReferralInput(StatesGroup):
    waiting_for_ref_link = State()

# ---------- КЛАВИАТУРЫ ----------
def main_menu(user_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛍 Товары", callback_data="menu_goods"),
        InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile")
    )
    builder.row(
        InlineKeyboardButton(text="👥 Рефералы", callback_data="menu_referrals"),
        InlineKeyboardButton(text="📞 Поддержка", callback_data="menu_support")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статус бота", callback_data="menu_status")
    )
    builder.row(
        InlineKeyboardButton(text="📚 Туториал", callback_data="menu_tutorial")
    )
    # Админ-кнопки видны только администратору
    if user_id == ADMIN_ID:
        builder.row(InlineKeyboardButton(text="🧪 Тестить (без оплаты)", callback_data="admin_test"))
        builder.row(InlineKeyboardButton(text="⭐️ Выдать рефералку", callback_data="admin_give_ref"))
        builder.row(InlineKeyboardButton(text="📋 Заказы на проверку", callback_data="admin_orders"))
    return builder.as_markup()

def goods_menu(user_id: int):
    user = get_user(user_id)
    current_refs = user[3] if user else 0

    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(
        text=f"🎮 Копия Блек Раша 2026 LITE (⭐️ {PRICE_STARS_PROJECT})",
        callback_data="buy_br_lite"
    ))

    if current_refs >= REFERRAL_COST:
        ref_button_text = f"👥 Потратить {REFERRAL_COST} рефералов (у вас: {current_refs} ✅)"
    else:
        ref_button_text = f"👥 Потратить {REFERRAL_COST} рефералов (у вас: {current_refs}/{REFERRAL_COST} ❌)"

    builder.row(InlineKeyboardButton(
        text=ref_button_text,
        callback_data="buy_with_refs"
    ))

    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def referrals_menu(user_id: int):
    """Меню рефералов с новыми кнопками"""
    user = get_user(user_id)
    if not user:
        current_refs = 0
        can_self = False
    else:
        current_refs = user[3]
        can_self = can_use_self_ref(user_id)

    builder = InlineKeyboardBuilder()

    # Кнопка "Отправить друзьям"
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    builder.row(InlineKeyboardButton(
        text="📤 Отправить друзьям",
        url=f"https://t.me/share/url?url={ref_link}&text=Присоединяйся к SANDER STARK! Создавай проекты!"
    ))

    # Кнопка "Купить 5 рефералов за 15 ⭐️"
    builder.row(InlineKeyboardButton(
        text=f"🛒 Купить 5 рефералов (⭐️ {PRICE_STARS_5_REFS})",
        callback_data="buy_5_refs"
    ))

    # Кнопка "Купить 10 рефералов за 30 ⭐️" со скидкой
    builder.row(InlineKeyboardButton(
        text=f"🔥 Купить 10 рефералов (⭐️ {PRICE_STARS_10_REFS}) СКИДКА!",
        callback_data="buy_10_refs"
    ))

    # Кнопка "Ввести реферальную ссылку"
    builder.row(InlineKeyboardButton(
        text="🔗 Ввести реферальную ссылку",
        callback_data="input_ref_link"
    ))

    # Кнопка "Использовать свою ссылку" (раз в день)
    if can_self:
        builder.row(InlineKeyboardButton(
            text="🎁 Использовать свою ссылку (+1 реферал) ✅",
            callback_data="use_self_ref"
        ))
    else:
        builder.row(InlineKeyboardButton(
            text="🎁 Использовать свою ссылку (уже использовано) ❌",
            callback_data="self_ref_blocked"
        ))

    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def cancel_button():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отказаться", callback_data="cancel_action"))
    return builder.as_markup()

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def get_user(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def can_use_self_ref(user_id: int) -> bool:
    """Проверяет, может ли пользователь сегодня использовать свою реферальную ссылку"""
    user = get_user(user_id)
    if not user:
        return False
    # Проверяем, что в кортеже достаточно элементов (last_self_ref_date на индексе 6)
    if len(user) < 7:
        return True  # Если поле отсутствует, разрешаем
    last_date = user[6]  # last_self_ref_date
    if last_date is None:
        return True
    today = date.today().isoformat()
    return last_date != today

def add_user(user_id: int, username: str, referrer_id: int = None):
    if get_user(user_id) is None:
        status = "Администратор" if user_id == ADMIN_ID else "Пользователь"
        cursor.execute("INSERT INTO users (user_id, username, referrer_id, status) VALUES (?, ?, ?, ?)",
                       (user_id, username, referrer_id, status))

        if referrer_id and referrer_id != user_id:
            add_referral(referrer_id, user_id, is_self_ref=False)
        elif referrer_id == user_id:
            if can_use_self_ref(user_id):
                add_referral(user_id, user_id, is_self_ref=True)
                cursor.execute("UPDATE users SET last_self_ref_date = ? WHERE user_id = ?",
                               (date.today().isoformat(), user_id))

        cursor.execute("UPDATE bot_stats SET total_uses = total_uses + 1")
        conn.commit()

def add_referral(referrer_id: int, referred_id: int, is_self_ref: bool = False):
    """Добавляет реферала"""
    today = date.today().isoformat()

    cursor.execute("""
        SELECT id FROM referrals 
        WHERE referrer_id = ? AND referred_id = ? AND date = ?
    """, (referrer_id, referred_id, today))

    if cursor.fetchone() is None:
        cursor.execute("""
            INSERT INTO referrals (referrer_id, referred_id, date, is_self_ref) 
            VALUES (?, ?, ?, ?)
        """, (referrer_id, referred_id, today, 1 if is_self_ref else 0))

        cursor.execute("""
            UPDATE users SET 
            referrals_count = referrals_count + 1, 
            balance_ref = balance_ref + 1 
            WHERE user_id = ?
        """, (referrer_id,))
        conn.commit()
        return True
    return False

def get_user_stats(user_id: int):
    user = get_user(user_id)
    if user:
        return {
            "user_id": user[0],
            "username": user[1],
            "referrals": user[3],
            "status": user[4],
            "balance_ref": user[5]
        }
    return None

def increment_orders(status="pending"):
    if status == "completed":
        cursor.execute("UPDATE bot_stats SET orders_completed = orders_completed + 1, orders_pending = orders_pending - 1")
    else:
        cursor.execute("UPDATE bot_stats SET orders_pending = orders_pending + 1")
    conn.commit()

def get_bot_stats():
    cursor.execute("SELECT * FROM bot_stats WHERE id = 1")
    row = cursor.fetchone()
    return {
        "total_uses": row[1],
        "orders_completed": row[2],
        "orders_pending": row[3]
    }

async def notify_admin(text: str, reply_markup=None):
    """Отправить уведомление админу в ЛС"""
    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        logging.error(f"Не удалось отправить админу: {e}")

def get_pending_orders():
    """Получить все заказы на проверку"""
    cursor.execute("""
        SELECT p.id, p.user_id, p.project_name, p.payment_method, p.payment_status, p.created_at, u.username 
        FROM projects p 
        LEFT JOIN users u ON p.user_id = u.user_id 
        WHERE p.admin_approved = 0 AND p.payment_status = 'оплачено'
    """)
    return cursor.fetchall()

def approve_order(order_id: int):
    """Подтвердить заказ администратором"""
    cursor.execute("UPDATE projects SET admin_approved = 1 WHERE id = ?", (order_id,))
    increment_orders("completed")
    conn.commit()

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Без username"

    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].split("_")[1])
        except:
            pass

    add_user(user_id, username, referrer_id)

    await message.answer(
        "♟️ <b>SANDER STARK</b> — твой личный создатель проектов!\n\n"
        "🤖 Используй кнопки внизу, чтобы управлять ботом.",
        reply_markup=main_menu(user_id),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "♟️ <b>SANDER STARK</b>\n\nВыбери действие:",
        reply_markup=main_menu(callback.from_user.id),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "cancel_action")
async def cancel_action(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено.\n\nВыбери, что хочешь сделать:",
        reply_markup=main_menu(callback.from_user.id)
    )
    await callback.answer()

# ---------- ТУТОРИАЛ ----------
@dp.callback_query(F.data == "menu_tutorial")
async def show_tutorial(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📚 <b>Туториал: Как создать проект</b>\n\n"
        "🚧 <b>В разработке!</b>\n"
        "⏰ Туториал будет включён <b>завтра вечером</b>.\n\n"
        "Следи за обновлениями! 🔔",
        reply_markup=back_to_main_button(),
        parse_mode="HTML"
    )
    await callback.answer()

def back_to_main_button():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

# ---------- ТОВАРЫ ----------
@dp.callback_query(F.data == "menu_goods")
async def show_goods(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    current_refs = user[3] if user else 0

    await callback.message.edit_text(
        f"🛍 <b>Товары</b>\n\n"
        f"🎮 <b>Копия Блек Раша 2026 LITE</b>\n"
        f"├─ ⭐️ За звёзды: <b>{PRICE_STARS_PROJECT} ⭐️</b>\n"
        f"└─ 👥 За рефералов: <b>{REFERRAL_COST} шт.</b> (у вас: {current_refs})\n\n"
        f"💡 <b>Как получить рефералов?</b>\n"
        f"• Приглашай друзей по реферальной ссылке (+1)\n"
        f"• Используй свою ссылку раз в день (+1)\n"
        f"• Купи рефералы в разделе «Рефералы»\n\n"
        f"Накопи <b>{REFERRAL_COST} шт.</b> и получи проект <b>БЕСПЛАТНО!</b>\n\n"
        f"⚠️ После оплаты заказ проверяется администратором.\n\n"
        f"Выбери способ оплаты:",
        reply_markup=goods_menu(callback.from_user.id),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "buy_br_lite")
async def buy_with_stars(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(payment_method="stars")
    await state.set_state(ProjectCreation.entering_name)
    await callback.message.edit_text(
        "📝 Введи <b>название проекта</b>:",
        reply_markup=cancel_button(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "buy_with_refs")
async def buy_with_referrals(callback: types.CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)

    if not user or user[3] < REFERRAL_COST:
        await callback.answer(
            f"❌ Недостаточно рефералов! Нужно {REFERRAL_COST}, у вас {user[3] if user else 0}",
            show_alert=True
        )
        return

    await state.update_data(payment_method="referrals")
    await state.set_state(ProjectCreation.entering_name)
    await callback.message.edit_text(
        f"👥 <b>Оплата рефералами</b>\n\n"
        f"📝 Введи <b>название проекта</b>:\n"
        f"(Спишется {REFERRAL_COST} рефералов)",
        reply_markup=cancel_button(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(StateFilter(ProjectCreation.entering_name))
async def process_project_name(message: Message, state: FSMContext):
    project_name = message.text
    data = await state.get_data()
    method = data.get("payment_method")

    if method == "referrals":
        user = get_user(message.from_user.id)
        if not user or user[3] < REFERRAL_COST:
            await message.answer(
                "❌ Ошибка: недостаточно рефералов! Операция отменена.",
                reply_markup=main_menu(message.from_user.id)
            )
            await state.clear()
            return

        cursor.execute("UPDATE users SET referrals_count = referrals_count - ? WHERE user_id = ?",
                       (REFERRAL_COST, message.from_user.id))

        cursor.execute("""
            INSERT INTO projects (user_id, project_name, payment_method, payment_status, admin_approved) 
            VALUES (?, ?, ?, 'оплачено', 0)
        """, (message.from_user.id, project_name, "referrals"))
        conn.commit()
        increment_orders("pending")

        # Уведомление админу с кнопкой "Принять"
        admin_kb = InlineKeyboardBuilder()
        cursor.execute("SELECT last_insert_rowid()")
        order_id = cursor.fetchone()[0]
        admin_kb.row(InlineKeyboardButton(
            text="✅ Принять заказ",
            callback_data=f"approve_order_{order_id}"
        ))

        user_data = get_user(message.from_user.id)
        await notify_admin(
            f"🆕 <b>Новый проект (Рефералы)</b>\n"
            f"🆔 Заказ #{order_id}\n"
            f"👤 Username: @{message.from_user.username or 'нет'}\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"📛 Проект: {project_name}\n"
            f"💳 Статус: ОПЛАЧЕНО\n"
            f"👥 Осталось рефералов: {user_data[3]}\n"
            f"🎁 Создатель: {ADMIN_USERNAME}\n\n"
            f"⏳ <b>Ожидает подтверждения!</b>",
            reply_markup=admin_kb.as_markup()
        )

        await message.answer(
            f"✅ Проект <b>«{project_name}»</b> успешно создан!\n"
            f"💳 Оплачено: {REFERRAL_COST} рефералами\n"
            f"🎁 Создатель: {ADMIN_USERNAME}\n\n"
            f"⏳ <b>Ожидайте подтверждения администратора!</b>",
            reply_markup=main_menu(message.from_user.id),
            parse_mode="HTML"
        )
        await state.clear()
        return

    elif method == "stars":
        await state.update_data(project_name=project_name)
        await state.set_state(ProjectCreation.confirm_payment)

        await message.answer_invoice(
            title="Создание проекта",
            description=f"Проект: {project_name}\nСоздатель: {ADMIN_USERNAME}",
            payload=f"project_{message.from_user.id}_{datetime.now().timestamp()}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Создание проекта", amount=PRICE_STARS_PROJECT)],
            start_parameter="create_project",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            protect_content=False
        )

    elif method == "admin_test":
        cursor.execute("""
            INSERT INTO projects (user_id, project_name, payment_method, payment_status, admin_approved) 
            VALUES (?, ?, ?, 'админ_тест', 1)
        """, (message.from_user.id, project_name, "admin_test"))
        conn.commit()
        increment_orders("completed")

        await notify_admin(
            f"🧪 <b>Админ-тест проекта</b>\n"
            f"👤 Username: @{message.from_user.username or 'нет'}\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"📛 Проект: {project_name}\n"
            f"💳 Статус: АДМИН-ТЕСТ\n"
            f"🎁 Создатель: {ADMIN_USERNAME}"
        )

        await message.answer(
            f"✅ <b>Тестовый проект создан!</b>\n"
            f"📛 Название: <b>«{project_name}»</b>\n"
            f"💳 Статус: без оплаты (админ-тест)\n"
            f"🎁 Создатель: {ADMIN_USERNAME}\n\n"
            f"🔗 Доступ в канал:\n{PRIVATE_CHANNEL_LINK}",
            reply_markup=main_menu(message.from_user.id),
            parse_mode="HTML"
        )
        await state.clear()

# ---------- РЕФЕРАЛЫ ----------
@dp.callback_query(F.data == "menu_referrals")
async def show_referrals(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

    stats = get_user_stats(user_id)
    referrals_count = stats['referrals'] if stats else 0

    can_self = can_use_self_ref(user_id)
    self_ref_status = "✅ Доступно" if can_self else "❌ Уже использовано сегодня"

    await callback.message.edit_text(
        f"👥 <b>Рефералы</b>\n\n"
        f"🔢 У тебя: <b>{referrals_count}</b> рефералов\n"
        f"🎯 Для бесплатного проекта: <b>{REFERRAL_COST}</b> шт.\n\n"
        f"📤 <b>Отправить друзьям</b> — поделись ссылкой\n"
        f"🛒 <b>Купить 5 рефералов</b> — {PRICE_STARS_5_REFS} ⭐️\n"
        f"🔥 <b>Купить 10 рефералов</b> — {PRICE_STARS_10_REFS} ⭐️ (СКИДКА!)\n"
        f"🔗 <b>Ввести ссылку</b> — активируй чужую ссылку\n"
        f"🎁 <b>Своя ссылка</b> — раз в день: {self_ref_status}\n\n"
        f"🔗 Твоя ссылка:\n<code>{ref_link}</code>",
        reply_markup=referrals_menu(user_id),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "buy_5_refs")
async def buy_5_refs(callback: types.CallbackQuery):
    await callback.message.answer_invoice(
        title="Покупка 5 рефералов",
        description="Получи +5 рефералов для использования в боте",
        payload=f"buy_5_refs_{callback.from_user.id}_{datetime.now().timestamp()}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="5 рефералов", amount=PRICE_STARS_5_REFS)],
        start_parameter="buy_5_referrals",
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        protect_content=False
    )
    await callback.answer("💳 Выставлен счёт на 5 рефералов")

@dp.callback_query(F.data == "buy_10_refs")
async def buy_10_refs(callback: types.CallbackQuery):
    await callback.message.answer_invoice(
        title="Покупка 10 рефералов 🔥",
        description="Получи +10 рефералов со скидкой!",
        payload=f"buy_10_refs_{callback.from_user.id}_{datetime.now().timestamp()}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="10 рефералов (скидка)", amount=PRICE_STARS_10_REFS)],
        start_parameter="buy_10_referrals",
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        protect_content=False
    )
    await callback.answer("🔥 Выставлен счёт на 10 рефералов со скидкой!")

@dp.callback_query(F.data == "input_ref_link")
async def input_ref_link_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ReferralInput.waiting_for_ref_link)
    await callback.message.edit_text(
        "🔗 <b>Введи реферальную ссылку</b>\n\n"
        "Отправь ссылку, которую получил от друга.\n"
        f"Формат: <code>https://t.me/{BOT_USERNAME}?start=ref_123456789</code>\n\n"
        "⚠️ Нельзя использовать свою ссылку через этот раздел!",
        reply_markup=cancel_button(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(StateFilter(ReferralInput.waiting_for_ref_link))
async def process_ref_link_input(message: Message, state: FSMContext):
    text = message.text.strip()

    if f"t.me/{BOT_USERNAME}?start=ref_" in text or f"telegram.me/{BOT_USERNAME}?start=ref_" in text:
        try:
            ref_id_str = text.split("ref_")[1].split()[0]
            referrer_id = int(ref_id_str)
            user_id = message.from_user.id

            if referrer_id == user_id:
                await message.answer(
                    "❌ Нельзя использовать свою реферальную ссылку через этот раздел!\n"
                    "Используй кнопку «🎁 Использовать свою ссылку» (раз в день).",
                    reply_markup=main_menu(user_id)
                )
                await state.clear()
                return

            referrer = get_user(referrer_id)
            if not referrer:
                await message.answer(
                    "❌ Пользователь с таким ID не найден в боте!",
                    reply_markup=main_menu(user_id)
                )
                await state.clear()
                return

            success = add_referral(referrer_id, user_id)

            if success:
                await message.answer(
                    f"✅ Реферальная ссылка активирована!\n"
                    f"Пользователь @{referrer[1] or 'без username'} получил +1 реферала.",
                    reply_markup=main_menu(user_id)
                )
            else:
                await message.answer(
                    "⚠️ Ты уже активировал эту реферальную ссылку сегодня.",
                    reply_markup=main_menu(user_id)
                )

        except (ValueError, IndexError):
            await message.answer(
                "❌ Неверный формат ссылки!",
                reply_markup=main_menu(user_id)
            )

        await state.clear()
    else:
        await message.answer(
            "❌ Неверная ссылка! Отправь корректную реферальную ссылку.",
            reply_markup=cancel_button()
        )

@dp.callback_query(F.data == "use_self_ref")
async def use_self_ref(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    if not can_use_self_ref(user_id):
        await callback.answer("❌ Ты уже использовал свою ссылку сегодня!", show_alert=True)
        return

    success = add_referral(user_id, user_id, is_self_ref=True)

    if success:
        cursor.execute("UPDATE users SET last_self_ref_date = ? WHERE user_id = ?",
                       (date.today().isoformat(), user_id))
        conn.commit()

        user = get_user(user_id)
        await callback.message.edit_text(
            f"🎁 <b>Ежедневный бонус получен!</b>\n\n"
            f"+1 реферал начислен!\n"
            f"🔢 Теперь у тебя: <b>{user[3]}</b> рефералов\n\n"
            f"Приходи завтра снова!",
            reply_markup=main_menu(user_id),
            parse_mode="HTML"
        )
        await callback.answer("✅ +1 реферал!")
    else:
        await callback.answer("⚠️ Сегодня уже получен бонус", show_alert=True)

@dp.callback_query(F.data == "self_ref_blocked")
async def self_ref_blocked(callback: types.CallbackQuery):
    await callback.answer("❌ Ты уже использовал свою ссылку сегодня. Приходи завтра!", show_alert=True)

# ---------- АДМИН: ЗАКАЗЫ НА ПРОВЕРКУ ----------
@dp.callback_query(F.data == "admin_orders")
async def show_admin_orders(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔️ Только для администратора!", show_alert=True)
        return

    pending_orders = get_pending_orders()

    if not pending_orders:
        await callback.message.edit_text(
            "📋 <b>Заказы на проверку</b>\n\n"
            "✅ Нет заказов, ожидающих подтверждения.",
            reply_markup=back_to_main_button(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    text = "📋 <b>Заказы на проверку:</b>\n\n"
    for order in pending_orders:
        order_id, user_id, project_name, pay_method, pay_status, created_at, username = order
        text += (
            f"🆔 <b>Заказ #{order_id}</b>\n"
            f"👤 Username: @{username or 'нет'}\n"
            f"🆔 ID: {user_id}\n"
            f"📛 Проект: {project_name}\n"
            f"💳 Метод: {pay_method}\n"
            f"📅 Дата: {created_at}\n\n"
        )

    # Создаём кнопки для каждого заказа
    builder = InlineKeyboardBuilder()
    for order in pending_orders:
        order_id = order[0]
        builder.row(InlineKeyboardButton(
            text=f"✅ Принять заказ #{order_id}",
            callback_data=f"approve_order_{order_id}"
        ))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))

    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("approve_order_"))
async def approve_order_handler(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔️ Только для администратора!", show_alert=True)
        return

    order_id = int(callback.data.split("_")[2])
    approve_order(order_id)

    # Получаем данные заказа
    cursor.execute("""
        SELECT p.user_id, p.project_name, u.username 
        FROM projects p 
        LEFT JOIN users u ON p.user_id = u.user_id 
        WHERE p.id = ?
    """, (order_id,))
    order = cursor.fetchone()

    if order:
        user_id = order[0]
        project_name = order[1]
        username = order[2]

        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"🎉 <b>Твой заказ одобрен!</b>\n\n"
                f"📛 Проект: <b>«{project_name}»</b>\n"
                f"✅ Администратор подтвердил создание проекта.\n\n"
                f"🔗 Доступ в приватный канал:\n{PRIVATE_CHANNEL_LINK}",
                parse_mode="HTML"
            )
        except:
            pass

        await notify_admin(
            f"✅ <b>Заказ #{order_id} одобрен!</b>\n"
            f"👤 Пользователь: @{username or 'нет'}\n"
            f"📛 Проект: {project_name}"
        )

    await callback.message.edit_text(
        f"✅ Заказ #{order_id} успешно принят!",
        reply_markup=back_to_main_button()
    )
    await callback.answer("✅ Заказ принят!")

# ---------- АДМИН: ТЕСТИРОВАНИЕ ----------
@dp.callback_query(F.data == "admin_test")
async def admin_test_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔️ Только для администратора!", show_alert=True)
        return

    await state.update_data(payment_method="admin_test")
    await state.set_state(ProjectCreation.entering_name)
    await callback.message.edit_text(
        "🧪 <b>Режим тестирования (без оплаты)</b>\n\n"
        "📝 Введи <b>название проекта</b>:",
        reply_markup=cancel_button(),
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- АДМИН: ВЫДАТЬ РЕФЕРАЛКУ ----------
@dp.callback_query(F.data == "admin_give_ref")
async def admin_give_ref_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔️ Только для администратора!", show_alert=True)
        return

    await state.set_state(AdminGiveRef.waiting_for_user_id)
    await callback.message.edit_text(
        "⭐️ <b>Выдача рефералок</b>\n\n"
        "Введи <b>ID пользователя</b>, которому хочешь начислить рефералы:",
        reply_markup=cancel_button(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(StateFilter(AdminGiveRef.waiting_for_user_id))
async def process_admin_give_ref_user(message: Message, state: FSMContext):
    try:
        target_user_id = int(message.text.strip())
        target_user = get_user(target_user_id)

        if not target_user:
            await message.answer("❌ Пользователь с таким ID не найден в базе бота!")
            return

        await state.update_data(target_user_id=target_user_id)
        await state.set_state(AdminGiveRef.waiting_for_amount)

        target_username = f"@{target_user[1]}" if target_user[1] else "без username"
        await message.answer(
            f"👤 Пользователь: {target_username} (ID: {target_user_id})\n"
            f"Текущие рефералы: {target_user[3]}\n\n"
            "📝 Введи <b>количество рефералов</b> для начисления:",
            reply_markup=cancel_button(),
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Пожалуйста, введи корректный числовой ID!")

@dp.message(StateFilter(AdminGiveRef.waiting_for_amount))
async def process_admin_give_ref_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Количество должно быть больше 0!")
            return

        data = await state.get_data()
        target_user_id = data.get("target_user_id")

        cursor.execute("UPDATE users SET referrals_count = referrals_count + ?, balance_ref = balance_ref + ? WHERE user_id = ?",
                       (amount, amount, target_user_id))
        conn.commit()

        target_user = get_user(target_user_id)
        target_username = f"@{target_user[1]}" if target_user[1] else "без username"

        await notify_admin(
            f"⭐️ <b>Выданы рефералы</b>\n"
            f"👤 Кому: {target_username} (ID: {target_user_id})\n"
            f"🔢 Количество: +{amount}\n"
            f"📊 Теперь у пользователя: {target_user[3]} рефералов"
        )

        try:
            await bot.send_message(
                target_user_id,
                f"🎉 <b>Поздравляем!</b>\n"
                f"Администратор начислил тебе +{amount} рефералов!\n"
                f"📊 Теперь у тебя: {target_user[3]} рефералов",
                parse_mode="HTML"
            )
        except:
            pass

        await message.answer(
            f"✅ Успешно выдано +{amount} рефералов пользователю {target_username}",
            reply_markup=main_menu(message.from_user.id)
        )
        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, введи корректное число!")

# ---------- ПРОФИЛЬ ----------
@dp.callback_query(F.data == "menu_profile")
async def show_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    stats = get_user_stats(user_id)

    if stats:
        profile_text = (
            f"👤 <b>Профиль</b>\n\n"
            f"🆔 ID: <code>{stats['user_id']}</code>\n"
            f"📛 Username: @{stats['username'] or 'нет'}\n"
            f"⭐️ Статус: <b>{stats['status']}</b>\n"
            f"👥 Рефералов: {stats['referrals']}"
        )
    else:
        profile_text = "❌ Профиль не найден"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))

    await callback.message.edit_text(
        profile_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- ПОДДЕРЖКА ----------
class SupportMessage(StatesGroup):
    waiting_for_text = State()

@dp.callback_query(F.data == "menu_support")
async def support_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SupportMessage.waiting_for_text)
    await callback.message.edit_text(
        "📞 <b>Поддержка</b>\n\n"
        "Напиши сообщение, и администратор свяжется с тобой.",
        reply_markup=cancel_button(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(StateFilter(SupportMessage.waiting_for_text))
async def process_support_message(message: Message, state: FSMContext):
    user = message.from_user
    support_text = message.text

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="✉️ Ответить пользователю",
        url=f"tg://user?id={user.id}"
    ))

    await notify_admin(
        f"📞 <b>Сообщение в поддержку</b>\n"
        f"👤 От: @{user.username or 'нет'} (ID: <code>{user.id}</code>)\n\n"
        f"💬 <b>Сообщение:</b>\n{support_text}"
    )

    await bot.send_message(
        ADMIN_ID,
        "Для быстрого ответа нажми кнопку ниже 👇",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

    await message.answer(
        "✅ Твоё сообщение отправлено! Ожидай ответа.",
        reply_markup=main_menu(message.from_user.id)
    )
    await state.clear()

# ---------- СТАТУС БОТА ----------
@dp.callback_query(F.data == "menu_status")
async def show_status(callback: types.CallbackQuery):
    stats = get_bot_stats()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))

    await callback.message.edit_text(
        f"📊 <b>Статус бота</b>\n\n"
        f"👥 Всего использовали бота: <b>{stats['total_uses']}</b>\n"
        f"✅ Заказов принято: <b>{stats['orders_completed']}</b>\n"
        f"⏳ Ожидает статуса: <b>{stats['orders_pending']}</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

# ---------- ОПЛАТА ЗВЁЗДАМИ ----------
@dp.pre_checkout_query()
async def on_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def on_successful_payment(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload

    if payload.startswith("project_"):
        data = await state.get_data()
        project_name = data.get("project_name", "Без названия")

        cursor.execute("""
            INSERT INTO projects (user_id, project_name, payment_method, payment_status, admin_approved) 
            VALUES (?, ?, ?, 'оплачено', 0)
        """, (user_id, project_name, "stars"))
        conn.commit()
        increment_orders("pending")

        # Уведомление админу с кнопкой "Принять"
        admin_kb = InlineKeyboardBuilder()
        cursor.execute("SELECT last_insert_rowid()")
        order_id = cursor.fetchone()[0]
        admin_kb.row(InlineKeyboardButton(
            text="✅ Принять заказ",
            callback_data=f"approve_order_{order_id}"
        ))

        user = get_user(user_id)
        await notify_admin(
            f"🆕 <b>Новый проект (Звёзды)</b>\n"
            f"🆔 Заказ #{order_id}\n"
            f"👤 Username: @{message.from_user.username or 'нет'}\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"📛 Проект: {project_name}\n"
            f"💳 Статус: ОПЛАЧЕНО\n"
            f"👥 Рефералов: {user[3] if user else 0}\n"
            f"🎁 Создатель: {ADMIN_USERNAME}\n\n"
            f"⏳ <b>Ожидает подтверждения!</b>",
            reply_markup=admin_kb.as_markup()
        )

        await message.answer(
            f"✅ <b>Оплата прошла успешно!</b>\n\n"
            f"📛 Проект: <b>«{project_name}»</b>\n"
            f"💳 Оплачено: {PRICE_STARS_PROJECT} ⭐️\n"
            f"🎁 Создатель: {ADMIN_USERNAME}\n\n"
            f"⏳ <b>Ожидайте подтверждения администратора!</b>",
            reply_markup=main_menu(user_id),
            parse_mode="HTML"
        )
        await state.clear()

    elif payload.startswith("buy_5_refs_"):
        cursor.execute("UPDATE users SET referrals_count = referrals_count + 5, balance_ref = balance_ref + 5 WHERE user_id = ?",
                       (user_id,))
        conn.commit()

        user = get_user(user_id)
        await message.answer(
            f"✅ <b>Покупка успешна!</b>\n\n"
            f"🛒 Куплено: 5 рефералов\n"
            f"💳 Оплачено: {PRICE_STARS_5_REFS} ⭐️\n"
            f"📊 Теперь у тебя: <b>{user[3]}</b> рефералов",
            reply_markup=main_menu(user_id),
            parse_mode="HTML"
        )

    elif payload.startswith("buy_10_refs_"):
        cursor.execute("UPDATE users SET referrals_count = referrals_count + 10, balance_ref = balance_ref + 10 WHERE user_id = ?",
                       (user_id,))
        conn.commit()

        user = get_user(user_id)
        await message.answer(
            f"🔥 <b>Покупка успешна!</b>\n\n"
            f"🛒 Куплено: 10 рефералов (со скидкой!)\n"
            f"💳 Оплачено: {PRICE_STARS_10_REFS} ⭐️\n"
            f"📊 Теперь у тебя: <b>{user[3]}</b> рефералов\n\n"
            f"💡 Ты сэкономил звёзды!",
            reply_markup=main_menu(user_id),
            parse_mode="HTML"
        )

# ---------- ЗАПУСК ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())