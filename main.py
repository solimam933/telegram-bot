import sqlite3
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, PreCheckoutQueryHandler, filters
from telegram.request import HTTPXRequest

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TOKEN")
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

    await update.message.reply_text("👋 مرحباً بك في بوت بيع النجوم", reply_markup=InlineKeyboardMarkup(keyboard))


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
            "4️⃣ ادفع من خلال Telegram\n"
            "5️⃣ ابعت بيانات الاستلام\n\n"
            "⏳ يتم مراجعة الطلب وتحويله"
        )

    elif q.data == "orders" and update.effective_user.id == ADMIN_ID:
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("SELECT * FROM orders WHERE status='pending'")
        orders = c.fetchall()
        conn.close()

        if not orders:
            await q.message.reply_text("❌ لا يوجد طلبات")
            return

        for o in orders:
            kb = [[
                InlineKeyboardButton("✅ تم الدفع", callback_data=f"done_{o[0]}"),
                InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{o[0]}")
            ]]
            await q.message.reply_text(
                f"👤 @{o[2]}\n⭐ {o[3]}\n💰 {o[4]}\n📱 {o[6]}\n💳 {o[5]}",
                reply_markup=InlineKeyboardMarkup(kb)
            )

    elif q.data.startswith("done_"):
        order_id = int(q.data.split("_")[1])
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("SELECT user_id, amount, address FROM orders WHERE id=?", (order_id,))
        data = c.fetchone()

        if not data:
            await q.message.reply_text("❌ الطلب غير موجود")
            return

        c.execute("UPDATE orders SET status='done' WHERE id=?", (order_id,))
        conn.commit()
        conn.close()

        await context.bot.send_message(data[0], f"✅ تم تحويل {data[1]} إلى {data[2]}")
        await q.message.reply_text("✅ تم الدفع")

    elif q.data.startswith("cancel_"):
        order_id = int(q.data.split("_")[1])
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("SELECT user_id, stars FROM orders WHERE id=?", (order_id,))
        data = c.fetchone()

        if not data:
            await q.message.reply_text("❌ الطلب غير موجود")
            return

        user_id, stars = data

        c.execute("UPDATE orders SET status='cancelled' WHERE id=?", (order_id,))
        conn.commit()
        conn.close()

        await context.bot.send_invoice(
            chat_id=user_id,
            title="Refund Stars",
            description="Refund your stars",
            payload="refund",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Refund", stars)]
        )

        await context.bot.send_message(user_id, "❌ تم إلغاء الطلب وتم إعادة النجوم")
        await q.message.reply_text("❌ تم الإلغاء + Refund")


# ========= MESSAGES =========
async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    msg_id = update.message.message_id
    if msg_id in processed_messages:
        return
    processed_messages.add(msg_id)

    user = update.effective_user

    if not BOT_ACTIVE and user.id != ADMIN_ID:
        await update.message.reply_text("🚧 البوت تحت الصيانة")
        return

    step = context.user_data.get("step")
    text = update.message.text

    if step == "broadcast" and user.id == ADMIN_ID:
        for (uid,) in get_users():
            try:
                await context.bot.send_message(uid, text)
            except:
                pass

        context.user_data.clear()
        await update.message.reply_text("✅ تم الإرسال")

    elif step == "stars":
        try:
            stars = int(text)

            if stars < 100 or stars % 50 != 0:
                await update.message.reply_text("❌ لازم 100+ ومضاعفات 50")
                return

            context.user_data["stars"] = stars

            await context.bot.send_invoice(
                chat_id=user.id,
                title="Pay Stars",
                description=f"Pay {stars} stars",
                payload="stars_payment",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice("Stars", stars)]
            )

        except:
            await update.message.reply_text("❌ ابعت رقم صحيح")

    elif step == "address":
        stars = context.user_data["stars"]
        method = context.user_data["method"]
        amount = calc_price(stars, method)

        conn = sqlite3.connect("bot.db")
        c = conn.cursor()

        c.execute(
            "INSERT INTO orders VALUES (NULL,?,?,?,?,?,?,?)",
            (user.id, user.username, stars, amount, method, text, "pending")
        )

        order_id = c.lastrowid
        conn.commit()
        conn.close()

        context.user_data.clear()

        await update.message.reply_text("⏳ يتم مراجعة طلبك")

        kb = [[
            InlineKeyboardButton("✅ تم الدفع", callback_data=f"done_{order_id}"),
            InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{order_id}")
        ]]

        await context.bot.send_message(
            ADMIN_ID,
            f"📥 طلب جديد\n\n"
            f"👤 @{user.username}\n"
            f"⭐ {stars}\n"
            f"💰 {amount}\n"
            f"📱 {text}\n"
            f"💳 {method}",
            reply_markup=InlineKeyboardMarkup(kb)
        )


# ========= PAYMENT =========
async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["step"] = "address"

    method = context.user_data.get("method")

    if method == "vodafone":
        await update.message.reply_text("📩 ابعت رقم Vodafone Cash")
    else:
        await update.message.reply_text("📩 ابعت عنوان USDT (Aptos)")


# ========= MAIN =========
def main():
    init_db()

    request = HTTPXRequest(connect_timeout=60, read_timeout=60)
    app = ApplicationBuilder().token(TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payment_success))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.SUCCESSFUL_PAYMENT, messages))

    print("BOT RUNNING...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
