import sqlite3
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    PreCheckoutQueryHandler,
    filters
)

logging.basicConfig(level=logging.INFO)

# TOKEN
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ TOKEN مش موجود في Variables")

TOKEN = str(TOKEN).strip()

ADMIN_ID = 5403590752

BOT_ACTIVE = True
processed_messages = set()

# ========= DATABASE =========
def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        stars INTEGER,
        amount REAL,
        method TEXT,
        address TEXT,
        status TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY
    )""")

    conn.commit()
    conn.close()


def add_user(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def get_users():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    return users


# ========= PRICE =========
def calc_price(stars, method):
    if method == "vodafone":
        if 100 <= stars <= 500:
            return stars * 0.5
        elif 500 < stars <= 999:
            return stars * 0.53
        else:
            return (stars / 1000) * 550
    else:
        if 100 <= stars <= 500:
            return stars * 0.01
        elif 500 < stars <= 999:
            return stars * 0.0105
        else:
            return (stars / 1000) * 11


# ========= START =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user.id)

    keyboard = [
        [InlineKeyboardButton("⭐️ بيع نجوم", callback_data="sell")],
        [InlineKeyboardButton("💰 اسعار النجوم", callback_data="prices")],
        [InlineKeyboardButton("📘 طريقة الاستخدام", callback_data="how")]
    ]

    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("📥 الطلبات", callback_data="orders")])
        keyboard.append([InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")])
        keyboard.append([
            InlineKeyboardButton("🔴 إيقاف", callback_data="off"),
            InlineKeyboardButton("🟢 تشغيل", callback_data="on")
        ])

    await update.message.reply_text(
        "👋 مرحباً بك في بوت بيع النجوم",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ========= BUTTONS =========
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOT_ACTIVE
    q = update.callback_query
    await q.answer()

    if q.data == "off" and update.effective_user.id == ADMIN_ID:
        BOT_ACTIVE = False
        await q.message.reply_text("🔴 تم إيقاف البوت")

    elif q.data == "on" and update.effective_user.id == ADMIN_ID:
        BOT_ACTIVE = True
        await q.message.reply_text("🟢 تم تشغيل البوت")

    elif q.data == "broadcast" and update.effective_user.id == ADMIN_ID:
        context.user_data["step"] = "broadcast"
        await q.message.reply_text("✉️ ابعت الرسالة")

    elif q.data == "sell":
        keyboard = [
            [InlineKeyboardButton("Vodafone Cash", callback_data="choose_vodafone")],
            [InlineKeyboardButton("USDT", callback_data="choose_usdt")]
        ]
        await q.message.reply_text("اختر طريقة الدفع", reply_markup=InlineKeyboardMarkup(keyboard))

    elif q.data.startswith("choose_"):
        method = q.data.split("_")[1]
        context.user_data["method"] = method
        context.user_data["step"] = "stars"
        await q.message.reply_text("📩 اكتب عدد النجوم (100 ومضاعفات 50)")

    elif q.data == "prices":
        await q.message.reply_text(
            "💰 اسعار النجوم:\n\n"
            "📱 Vodafone Cash:\n"
            "100 - 500 ⭐ = 0.5 جنيه / نجمة\n"
            "500 - 999 ⭐ = 0.53 جنيه / نجمة\n"
            "1000+ ⭐ = 550 جنيه لكل 1000\n\n"
            "💲 USDT:\n"
            "100 - 500 ⭐ = 0.01 USDT / نجمة\n"
            "500 - 999 ⭐ = 0.0105 USDT / نجمة\n"
            "1000+ ⭐ = 11 USDT لكل 1000"
        )

    elif q.data == "how":
        await q.message.reply_text(
            "📘 طريقة الاستخدام:\n\n"
            "1️⃣ اضغط بيع نجوم\n"
            "2️⃣ اختار طريقة الدفع\n"
            "3️⃣ اكتب عدد النجوم\n"
            "4️⃣ ادفع\n"
            "5️⃣ ابعت بيانات الاستلام"
        )


# ========= MESSAGES =========
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not BOT_ACTIVE:
        return

    user_id = update.effective_user.id
    text = update.message.text

    if context.user_data.get("step") == "broadcast" and user_id == ADMIN_ID:
        users = get_users()
        for user in users:
            try:
                await context.bot.send_message(chat_id=user[0], text=text)
            except:
                pass
        await update.message.reply_text("✅ تم الإرسال")
        context.user_data["step"] = None
        return

    if context.user_data.get("step") == "stars":
        try:
            stars = int(text)
            method = context.user_data.get("method")
            price = calc_price(stars, method)

            context.user_data["stars"] = stars
            context.user_data["price"] = price

            await update.message.reply_text(f"💰 السعر: {price}")
        except:
            await update.message.reply_text("❌ اكتب رقم صحيح")


# ========= PAYMENT =========
async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["step"] = "address"

    method = context.user_data.get("method")

    if method == "vodafone":
        await update.message.reply_text("📩 ابعت رقم Vodafone Cash")
    else:
        await update.message.reply_text("📩 ابعت عنوان USDT")


# ========= MAIN =========
def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.SUCCESSFUL_PAYMENT, messages))

    print("BOT RUNNING...")
    app.run_polling()


if __name__ == "__main__":
    main()
