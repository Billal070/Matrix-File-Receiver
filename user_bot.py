import logging
from datetime import datetime
import io

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
        [KeyboardButton("📁 ফাইল জমা দিন"),     KeyboardButton("📊 আমার সাবমিশন")],
        [KeyboardButton("💰 আমার পেমেন্ট"),      KeyboardButton("👤 আমার অ্যাকাউন্ট")],
        [KeyboardButton("ℹ️  সাহায্য")],
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

def pbar(val, total, w=10):
    if total == 0: return "░" * w
    f = round(val / total * w)
    return "█" * f + "░" * (w - f)

def pct(val, total):
    return round(val / total * 100) if total else 0

def get_badge(approved, total):
    if total == 0: return "🆕 নতুন সদস্য"
    rate = pct(approved, total)
    if rate >= 90: return "🏆 এক্সপার্ট"
    elif rate >= 70: return "⭐ অভিজ্ঞ"
    elif rate >= 40: return "📈 উন্নতিশীল"
    else: return "🌱 শিক্ষানবিস"


# ── /start ─────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    is_new = db.get_user(user.id) is None
    db.register_user(user.id, user.username, user.full_name)

    badge = "🆕 *নতুন অ্যাকাউন্ট তৈরি হয়েছে!*" if is_new else "🔄 _স্বাগতম ফিরে!_"

    await update.message.reply_text(
        f"〔 🔷 *{BOT_NAME}* 〕\n"
        f"{DIVIDER}\n\n"
        f"👋 হ্যালো, *{user.first_name}!*\n"
        f"{badge}\n\n"
        f"📌 *আপনি যা করতে পারবেন:*\n\n"
        f"  📁  `.xlsx` ফাইল পাঠিয়ে জমা দিন\n"
        f"  📊  সাবমিশনের স্ট্যাটাস ট্র্যাক করুন\n"
        f"  💰  পেমেন্ট হিস্ট্রি দেখুন\n"
        f"  👤  আপনার অ্যাকাউন্ট দেখুন\n\n"
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


# ── 👤 আমার অ্যাকাউন্ট ────────────────────────────────────────────────────────
async def btn_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_account(update)

async def cmd_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_account(update)

async def _show_account(update: Update):
    user    = update.effective_user
    db_user = db.get_user(user.id)

    if not db_user:
        db.register_user(user.id, user.username, user.full_name)
        db_user = db.get_user(user.id)

    # Data
    subs     = db.get_user_submissions(user.id)
    pays     = db.get_user_payments(user.id)
    total_s  = len(subs)
    approved = sum(1 for s in subs if s["status"] == "approved")
    pending  = sum(1 for s in subs if s["status"] == "pending")
    declined = sum(1 for s in subs if s["status"] == "declined")
    total_p  = sum(p["amount"] for p in pays)
    last_pay = pays[0] if pays else None
    last_sub = subs[0] if subs else None
    badge    = get_badge(approved, total_s)
    success  = pct(approved, total_s)

    text = (
        f"〔 👤 *আমার অ্যাকাউন্ট* 〕\n"
        f"{DIVIDER}\n\n"

        # ── Profile
        f"🙍 *নাম:*     {user.full_name}\n"
        f"🔗 *Username:* @{user.username or '—'}\n"
        f"🪪 *ID:*      `{user.id}`\n"
        f"📅 *যোগদান:*  {fmt_dt(db_user['registered_at'])}\n"
        f"🏅 *ব্যাজ:*   {badge}\n\n"

        f"{DIVIDER}\n\n"

        # ── Submissions
        f"📊 *সাবমিশন সারসংক্ষেপ:*\n"
        f"  📦 মোট:        *{total_s}*\n"
        f"  ✅ অনুমোদিত:  *{approved}*\n"
        f"  ⏳ অপেক্ষমান: *{pending}*\n"
        f"  ❌ বাতিল:      *{declined}*\n\n"
        f"  📈 সাফল্যের হার:\n"
        f"  {pbar(approved, total_s)} *{success}%*\n\n"
    )

    if last_sub:
        em = STATUS_EMOJI.get(last_sub["status"], "❓")
        text += (
            f"  🕐 সর্বশেষ সাবমিশন:\n"
            f"  {em} `{last_sub['sub_id']}` — _{STATUS_BN.get(last_sub['status'], '')}_\n\n"
        )

    text += f"{DIVIDER}\n\n"

    # ── Payments
    text += (
        f"💰 *পেমেন্ট সারসংক্ষেপ:*\n"
        f"  💵 মোট লেনদেন: *{len(pays)}* বার\n"
        f"  💎 মোট প্রাপ্তি: *{total_p:,.0f} ৳*\n"
    )

    if last_pay:
        text += (
            f"  🕐 সর্বশেষ পেমেন্ট:\n"
            f"  💲 *{last_pay['amount']:,.0f} ৳* — {fmt_dt(last_pay['sent_at'])}\n"
        )

    text += f"\n{DIVIDER}"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 সাবমিশন", callback_data="acc_subs"),
            InlineKeyboardButton("💰 পেমেন্ট",  callback_data="acc_pays"),
        ]
    ])

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cb_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline button callbacks from account page."""
    q = update.callback_query
    await q.answer()
    if q.data == "acc_subs":
        await _show_status_from_query(q)
    elif q.data == "acc_pays":
        await _show_payments_from_query(q)

async def _show_status_from_query(q):
    user = q.from_user
    subs = db.get_user_submissions(user.id)
    if not subs:
        await q.message.reply_text("📭 *কোনো সাবমিশন নেই।*", parse_mode="Markdown"); return
    total    = len(subs)
    approved = sum(1 for s in subs if s["status"] == "approved")
    pending  = sum(1 for s in subs if s["status"] == "pending")
    declined = sum(1 for s in subs if s["status"] == "declined")
    text = (
        f"📊 *আমার সাবমিশন*\n{DIVIDER}\n\n"
        f"📦 মোট: *{total}*  ✅ *{approved}*  ⏳ *{pending}*  ❌ *{declined}*\n\n{DIVIDER}\n\n"
    )
    for sub in subs[:10]:
        em   = STATUS_EMOJI.get(sub["status"], "❓")
        s_bn = STATUS_BN.get(sub["status"], sub["status"])
        text += f"{em} *{sub['sub_id']}*\n   📄 `{sub['file_name']}`\n   📌 _{s_bn}_\n\n"
    await q.message.reply_text(text, parse_mode="Markdown")

async def _show_payments_from_query(q):
    user = q.from_user
    pays = db.get_user_payments(user.id)
    if not pays:
        await q.message.reply_text("💰 *কোনো পেমেন্ট নেই।*", parse_mode="Markdown"); return
    total = sum(p["amount"] for p in pays)
    text  = f"💰 *পেমেন্ট হিস্ট্রি*\n{DIVIDER}\n\n"
    for pay in pays[:10]:
        text += f"💵 *{pay['pay_id']}*\n   💲 *{pay['amount']:,.0f} ৳*\n   📅 {fmt_dt(pay['sent_at'])}\n\n"
    text += f"{DIVIDER}\n💎 *সর্বমোট: {total:,.0f} ৳*"
    await q.message.reply_text(text, parse_mode="Markdown")


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
        f"*🏅 ব্যাজ সিস্টেম:*\n"
        f"  🏆 এক্সপার্ট    → ৯০%+ সাফল্য\n"
        f"  ⭐ অভিজ্ঞ       → ৭০%+ সাফল্য\n"
        f"  📈 উন্নতিশীল   → ৪০%+ সাফল্য\n"
        f"  🌱 শিক্ষানবিস   → নতুন\n\n"
        f"*📌 Commands:*\n"
        f"  /start    — প্রধান মেনু\n"
        f"  /account  — আমার অ্যাকাউন্ট\n"
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

    doc   = update.message.document
    fname = doc.file_name or ""

    if not (fname.lower().endswith(".xlsx") or fname.lower().endswith(".xls")):
        await update.message.reply_text(
            f"❌ *ভুল ফাইল ফরম্যাট!*\n\n"
            f"_শুধুমাত্র_ `.xlsx` _বা_ `.xls` _গ্রহণযোগ্য।_",
            parse_mode="Markdown",
        )
        return

    proc    = await update.message.reply_text("⏳ _ফাইল প্রসেস হচ্ছে..._", parse_mode="Markdown")
    caption = update.message.caption or ""
    sub_id  = db.add_submission(user.id, doc.file_id, fname, caption)
    await proc.delete()

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

    # ── Notify Admin ──────────────────────────────────────────────────────────
    try:
        tg_file    = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        file_io    = io.BytesIO(file_bytes)
        file_io.name = fname

        async with Bot(token=ADMIN_BOT_TOKEN) as admin_bot:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅  Approve", callback_data=f"approve_{sub_id}"),
                InlineKeyboardButton("❌  Decline", callback_data=f"decline_{sub_id}"),
            ]])
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
        "💰 আমার পেমেন্ট",  "👤 আমার অ্যাকাউন্ট",
        "ℹ️  সাহায্য",
    }
    if (update.message.text or "") not in known:
        await update.message.reply_text(
            "❓ _বুঝতে পারিনি।_\n\n_নিচের মেনু ব্যবহার করুন।_",
            parse_mode="Markdown",
            reply_markup=MENU,
        )


# ── Text Button Dispatcher ────────────────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Single handler for all text — dispatches by button label."""
    text = (update.message.text or "").strip()

    if text == "📁 ফাইল জমা দিন":
        await btn_submit(update, context)
    elif text == "📊 আমার সাবমিশন":
        await _show_status(update)
    elif text == "💰 আমার পেমেন্ট":
        await _show_payments(update)
    elif text == "👤 আমার অ্যাকাউন্ট":
        await _show_account(update)
    elif "সাহায্য" in text:
        await _show_help(update)
    else:
        await update.message.reply_text(
            "❓ _বুঝতে পারিনি।_\n\n_নিচের মেনু ব্যবহার করুন।_",
            parse_mode="Markdown",
            reply_markup=MENU,
        )


# ── App Factory ────────────────────────────────────────────────────────────────
def create_user_app():
    app = Application.builder().token(USER_BOT_TOKEN).build()

    from telegram.ext import CallbackQueryHandler

    # Commands
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("payments", cmd_payments))
    app.add_handler(CommandHandler("account",  cmd_account))
    app.add_handler(CommandHandler("help",     cmd_help))

    # Files
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_photo))

    # Single text dispatcher — handles all buttons reliably
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Inline buttons from account page
    app.add_handler(CallbackQueryHandler(cb_account, pattern=r"^acc_"))

    return app
