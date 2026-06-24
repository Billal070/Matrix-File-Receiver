import logging
from datetime import datetime
import io  # ইন-মেমোরি ফাইল হ্যান্ডলিংয়ের জন্য

from telegram import (
    Update, Bot,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)

import database as db
from config import USER_BOT_TOKEN, ADMIN_BOT_TOKEN, ADMIN_TELEGRAM_ID, BOT_NAME, DIVIDER

logger = logging.getLogger(__name__)

# ── Persistent Menu ────────────────────────────────────────────────────────────
MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📁 ফাইল জমা দিন"),   KeyboardButton("📊 আমার সাবমিশন")],
        [KeyboardButton("💰 আমার পেমেন্ট"),    KeyboardButton("ℹ️  সাহায্য")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

STATUS_EMOJI = {"pending": "⏳", "approved": "✅", "declined": "❌"}
STATUS_BN    = {"pending": "অপেক্ষমান", "approved": "অনুমোদিত", "declined": "বাতিল"}


def fmt_dt(s):
    try:
        return datetime.fromisoformat(s).strftime("%d %b %Y  %I:%M %p")
    except Exception:
        return s or "N/A"


# ── /start ─────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    is_new = db.get_user(user.id) is None
    db.register_user(user.id, user.username, user.full_name)

    badge = "🆕 *নতুন অ্যাকাউন্ট তৈরি হয়েছে!*" if is_new else "🔄 _স্বাগতম!_"

    await update.message.reply_text(
        f"〔 🔷 *{BOT_NAME}* 〕\n"
        f"{DIVIDER}\n\n"
        f"👋 হ্যালো, *{user.first_name}!*\n"
        f"{badge}\n\n"
        f"📌 *আপনি যা করতে পারবেন:*\n\n"
        f"  📁  `.xlsx` ফাইল পাঠিয়ে জমা দিন\n"
        f"  📊  সাবমিশনের স্ট্যাটাস ট্র্যাক করুন\n"
        f"  💰  পেমেন্ট হিস্ট্রি দেখুন\n\n"
        f"{DIVIDER}\n"
        f"_নিচের মেনু থেকে যেকোনো অপশন বেছে নিন_ 👇",
        parse_mode="Markdown",
        reply_markup=MENU,
    )


# ── ফাইল জমা দিন ──────────────────────────────────────────────────────────────
async def btn_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📁 *ফাইল জমা দিন*\n"
        f"{DIVIDER}\n\n"
        f"✅ এখন আপনার *.xlsx* ফাইলটি পাঠান।\n\n"
        f"📌 *নিয়ম:*\n"
        f"  • শুধুমাত্র *.xlsx / .xls* গ্রহণযোগ্য\n"
        f"  • ফাইলের সাথে Caption দিতে পারেন\n"
        f"  • জমা হলে একটি Tracking ID পাবেন\n\n"
        f"_📎 ফাইল attach করে পাঠান_",
        parse_mode="Markdown",
    )


# ── আমার সাবমিশন ──────────────────────────────────────────────────────────────
async def btn_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_status(update)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_status(update)

async def _show_status(update: Update):
    user = update.effective_user
    subs = db.get_user_submissions(user.id)

    if not subs:
        await update.message.reply_text(
            f"📭 *কোনো সাবমিশন নেই।*\n\n"
            f"_'📁 ফাইল জমা দিন' বাটন চেপে শুরু করুন।_",
            parse_mode="Markdown",
        )
        return

    total    = len(subs)
    approved = sum(1 for s in subs if s["status"] == "approved")
    pending  = sum(1 for s in subs if s["status"] == "pending")
    declined = sum(1 for s in subs if s["status"] == "declined")

    text = (
        f"📊 *আমার সাবমিশন*\n"
        f"{DIVIDER}\n\n"
        f"📦 মোট:         *{total}*\n"
        f"✅ অনুমোদিত:   *{approved}*\n"
        f"⏳ অপেক্ষমান:  *{pending}*\n"
        f"❌ বাতিল:       *{declined}*\n\n"
        f"{DIVIDER}\n\n"
    )

    for sub in subs[:10]:
        em   = STATUS_EMOJI.get(sub["status"], "❓")
        s_bn = STATUS_BN.get(sub["status"], sub["status"])
        text += (
            f"{em} *{sub['sub_id']}*\n"
            f"   📄 `{sub['file_name']}`\n"
            f"   📅 {fmt_dt(sub['submitted_at'])}\n"
            f"   📌 _{s_bn}_\n"
        )
        if sub["admin_note"]:
            text += f"   💬 {sub['admin_note']}\n"
        text += "\n"

    if total > 10:
        text += f"_...আরও {total - 10}টি সাবমিশন রয়েছে।_"

    await update.message.reply_text(text, parse_mode="Markdown")


# ── আমার পেমেন্ট ──────────────────────────────────────────────────────────────
async def btn_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_payments(update)

async def cmd_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_payments(update)

async def _show_payments(update: Update):
    user = update.effective_user
    pays = db.get_user_payments(user.id)

    if not pays:
        await update.message.reply_text(
            f"💰 *কোনো পেমেন্ট নেই।*\n\n"
            f"_কাজ অনুমোদনের পর পেমেন্ট পাঠানো হবে।_",
            parse_mode="Markdown",
        )
        return

    total = sum(p["amount"] for p in pays)

    text = (
        f"💰 *আমার পেমেন্ট হিস্ট্রি*\n"
        f"{DIVIDER}\n\n"
        f"📦 মোট পেমেন্ট: *{len(pays)}* বার\n"
        f"💎 মোট পরিমাণ: *{total:,.0f} ৳*\n\n"
        f"{DIVIDER}\n\n"
    )

    for pay in pays[:10]:
        text += (
            f"💵 *{pay['pay_id']}*\n"
            f"   💲 *{pay['amount']:,.0f} টাকা*\n"
            f"   📅 {fmt_dt(pay['sent_at'])}\n"
        )
        if pay["note"]:
            text += f"   📝 _{pay['note']}_\n"
        text += "\n"

    text += f"{DIVIDER}\n💎 *সর্বমোট: {total:,.0f} টাকা*"
    await update.message.reply_text(text, parse_mode="Markdown")


# ── সাহায্য ───────────────────────────────────────────────────────────────────
async def btn_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_help(update)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_help(update)

async def _show_help(update: Update):
    await update.message.reply_text(
        f"ℹ️ *সাহায্য — {BOT_NAME}*\n"
        f"{DIVIDER}\n\n"
        f"*📁 ফাইল জমা দেওয়ার নিয়ম:*\n"
        f"  • শুধুমাত্র *.xlsx / .xls* ফাইল গ্রহণযোগ্য\n"
        f"  • Telegram এ File হিসেবে পাঠান\n"
        f"  • চাইলে Caption যোগ করতে পারেন\n\n"
        f"*📊 স্ট্যাটাসের অর্থ:*\n"
        f"  ⏳ অপেক্ষমান → অ্যাডমিন রিভিউ করেননি\n"
        f"  ✅ অনুমোদিত  → কাজ গ্রহণ হয়েছে\n"
        f"  ❌ বাতিল      → কাজ গ্রহণ হয়নি\n\n"
        f"*💰 পেমেন্ট:*\n"
        f"  অনুমোদনের পর অ্যাডমিন পেমেন্ট\n"
        f"  নোটিফিকেশন পাঠাবেন।\n\n"
        f"*📌 Commands:*\n"
        f"  /start    — প্রধান মেনু\n"
        f"  /status   — সাবমিশন দেখুন\n"
        f"  /payments — পেমেন্ট দেখুন\n\n"
        f"{DIVIDER}\n"
        f"_সমস্যায় অ্যাডমিনের সাথে যোগাযোগ করুন।_",
        parse_mode="Markdown",
    )


# ── File Handler ───────────────────────────────────────────────────────────────
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.get_user(user.id):
        db.register_user(user.id, user.username, user.full_name)

    doc = update.message.document
    fname = doc.file_name or ""

    if not (fname.lower().endswith(".xlsx") or fname.lower().endswith(".xls")):
        await update.message.reply_text(
            f"❌ *ভুল ফাইল ফরম্যাট!*\n\n"
            f"_শুধুমাত্র_ `.xlsx` _বা_ `.xls` _গ্রহণযোগ্য।_\n\n"
            f"📌 Excel ফাইল পাঠান।",
            parse_mode="Markdown",
        )
        return

    # Processing indicator
    proc = await update.message.reply_text(
        "⏳ _ফাইল প্রসেস হচ্ছে..._", parse_mode="Markdown"
    )

    caption = update.message.caption or ""
    sub_id  = db.add_submission(user.id, doc.file_id, fname, caption)

    await proc.delete()

    # Confirm to member
    await update.message.reply_text(
        f"〔 ✅ *সাবমিশন সফল!* 〕\n"
        f"{DIVIDER}\n\n"
        f"🆔 Tracking ID: `{sub_id}`\n"
        f"📄 ফাইল: `{fname}`\n"
        f"⏳ স্ট্যাটাস: *অপেক্ষমান*\n"
        f"🕐 সময়: {fmt_dt(datetime.now().isoformat())}\n\n"
        f"_অ্যাডমিন রিভিউ করলে আপনাকে জানানো হবে।_\n"
        f"📊 /status দিয়ে ট্র্যাক করুন।",
        parse_mode="Markdown",
        reply_markup=MENU,
    )

    # ── Notify Admin (FIXED: Byte Stream Download Bypass) ──────────────────────
    try:
        # User Bot এর সেশন ব্যবহার করে ফাইলটি মেমোরিতে ডাউনলোড করা হচ্ছে
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        
        # বাইট ডেটাকে ফাইলে রূপান্তর
        file_io = io.BytesIO(file_bytes)
        file_io.name = fname

        async with Bot(token=ADMIN_BOT_TOKEN) as admin_bot:
            keyboard  = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅  Approve", callback_data=f"approve_{sub_id}"),
                InlineKeyboardButton("❌  Decline", callback_data=f"decline_{sub_id}"),
            ]])
            # HTML mode — safe for filenames/usernames with special characters
            cap = (
                f"🔔 <b>নতুন সাবমিশন!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 <code>{sub_id}</code>\n"
                f"👤 <b>{user.full_name}</b>\n"
                f"   🔗 @{user.username or '—'}\n"
                f"   🪪 <code>{user.id}</code>\n"
                f"📄 <code>{fname}</code>\n"
                f"💬 {caption or 'caption নেই'}\n"
                f"🕐 {fmt_dt(datetime.now().isoformat())}"
            )
            # Admin bot এর মাধ্যমে নতুন বাইটস্ট্রিম ফাইল হিসেবে অ্যাডমিনকে পাঠানো হচ্ছে
            await admin_bot.send_document(
                chat_id=ADMIN_TELEGRAM_ID,
                document=file_io,
                caption=cap,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    except Exception as e:
        logger.error(f"Admin notify failed: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ *Photo হিসেবে নয়!*\n\n"
        "📎 _ফাইল হিসেবে attach করুন:_\n"
        "`Attach → File → .xlsx select করুন`",
        parse_mode="Markdown",
    )


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    known = {
        "📁 ফাইল জমা দিন", "📊 আমার সাবমিশন",
        "💰 আমার পেমেন্ট", "ℹ️  সাহায্য",
    }
    if (update.message.text or "") not in known:
        await update.message.reply_text(
            "❓ _বুঝতে পারিনি।_\n\n_নিচের মেনু ব্যবহার করুন।_",
            parse_mode="Markdown",
            reply_markup=MENU,
        )


# ── App Factory ────────────────────────────────────────────────────────────────
def create_user_app():
    app = Application.builder().token(USER_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("payments", cmd_payments))
    app.add_handler(CommandHandler("help",     cmd_help))

    # Keyboard buttons
    app.add_handler(MessageHandler(filters.Regex(r"^📁 ফাইল জমা দিন$"),   btn_submit))
    app.add_handler(MessageHandler(filters.Regex(r"^📊 আমার সাবমিশন$"),   btn_status))
    app.add_handler(MessageHandler(filters.Regex(r"^💰 আমার পেমেন্ট$"),   btn_payments))
    app.add_handler(MessageHandler(filters.Regex(r"^ℹ️  সাহায্য$"),       btn_help))

    # Files
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_photo))

    # Catch-all
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))

    return app
