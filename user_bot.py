import logging
from datetime import datetime, timedelta, timezone # BDT Timezone tracking
import io

from telegram import (
    Update, Bot,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler,
)

import database as db
from config import USER_BOT_TOKEN, ADMIN_BOT_TOKEN, ADMIN_TELEGRAM_ID, BOT_NAME, DIVIDER

logger = logging.getLogger(__name__)

# ── Persistent Menu (Translated to English) ────────────────────────────────────
MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📁 Submit File"),     KeyboardButton("📊 My Submissions")],
        [KeyboardButton("💰 My Payments"),      KeyboardButton("👤 My Account")],
        [KeyboardButton("ℹ️  Help")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

STATUS_EMOJI = {"pending": "⏳", "approved": "✅", "declined": "❌"}
STATUS_BN    = {"pending": "Pending", "approved": "Approved", "declined": "Declined"}


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
    if total == 0: return "🆕 New Member"
    rate = pct(approved, total)
    if rate >= 90: return "🏆 Expert"
    elif rate >= 70: return "⭐ Experienced"
    elif rate >= 40: return "📈 Rising"
    else: return "🌱 Beginner"

user_states = {}


# ── /start welcome message (Date Only - Time Excluded) ────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    is_new = db.get_user(user.id) is None
    db.register_user(user.id, user.username, user.full_name)

    db_user = db.get_user(user.id)
    
    # BDT অনুযায়ী শুধুমাত্র আজকের তারিখ (দিন মাস বছর) বের করার জন্য লাইব্রেরি
    from datetime import datetime, timedelta, timezone
    bdt_tz = timezone(timedelta(hours=6))
    
    try:
        if db_user and db_user['registered_at']:
            # সময় বাদ দিয়ে শুধুমাত্র তারিখ ফরম্যাট (যেমন: 25 Jun 2026) করা হচ্ছে
            joined_date = datetime.fromisoformat(db_user['registered_at']).strftime("%d %b %Y")
        else:
            joined_date = datetime.now(bdt_tz).strftime("%d %b %Y")
    except Exception:
        joined_date = datetime.now(bdt_tz).strftime("%d %b %Y")

    welcome_text = (
        f"💎 <b>Matrix File Receiver</b> 🤖\n"
        f"Welcome, <b>{user.full_name}</b> 👋\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"📅 <b>Member Since:</b> {joined_date}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"📂 File Submission\n"
        f"🤑 Withdraw Payments\n"
        f"🔔 Real-Time Notifications\n"
        f"🔒 Secure Processing\n"
        f"━━━━━━━━━━━━━━\n"
        f"🚀 🚀 Ready to get started?\n"
        f"Choose an option from the menu below.👇"
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=MENU,
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML", # HTML parsing enabled for clean bold and code styling
        reply_markup=MENU,
    )

# ── Submit File ────────────────────────────────────────────────────────────────
async def btn_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_submissions_open():
        await update.message.reply_text(
            f"⚠️ *Submissions are Closed!*\n"
            f"{DIVIDER}\n\n"
            f"We are currently not accepting new file submissions at this time.\n\n"
            f"📢 _You will be notified once submissions are open again._\n"
            f"Thank you for your cooperation! 🙏",
            parse_mode="Markdown",
        )
        return

    active_tasks = db.get_all_tasks()
    if not active_tasks:
        await update.message.reply_text(
            f"⚠️ *No Active Tasks!*\n"
            f"{DIVIDER}\n\n"
            f"There are currently no active work types set by the administrator.\n"
            f"Please wait until the administrator adds new work types.",
            parse_mode="Markdown",
        )
        return

    kb_buttons = []
    for task in active_tasks:
        kb_buttons.append([InlineKeyboardButton(f"📂 {task['task_name']}", callback_data=f"seltask_{task['id']}")])
    kb_buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_submit")])

    markup = InlineKeyboardMarkup(kb_buttons)

    await update.message.reply_text(
        f"📁 *Select Work Type*\n"
        f"{DIVIDER}\n\n"
        f"Please select which work file you want to submit from the options below:",
        parse_mode="Markdown",
        reply_markup=markup,
    )


# ── Callback handler for selecting task (Check Bangladesh Time Scheduled Window) ──
async def cb_select_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id

    task_id = int(q.data.replace("seltask_", ""))
    task = db.get_task_by_id(task_id)

    if not task:
        await q.message.reply_text("❌ Selected work type not found."); return

    # FIXED: বাংলাদেশ সময় (UTC+6) অনুযায়ী সাবমিশন সময় যাচাই করা
    bdt_tz = timezone(timedelta(hours=6))
    now_bdt = datetime.now(bdt_tz)
    current_time_str = now_bdt.strftime("%H:%M") # "HH:MM" 24h format

    start_time = task["start_time"] or "00:00"
    end_time = task["end_time"] or "23:59"

    # ডায়নামিক সময় তুলনা লজিক (মাঝরাত পার হওয়ার কেস সহ)
    is_open = False
    if start_time <= end_time:
        is_open = start_time <= current_time_str <= end_time
    else:
        is_open = current_time_str >= start_time or current_time_str <= end_time

    if not is_open:
        # ২৪-ঘণ্টা ফরম্যাট থেকে ১২-ঘণ্টা AM/PM এ রূপান্তর
        def format_12h(time_str):
            try:
                return datetime.strptime(time_str, "%H:%M").strftime("%I:%M %p")
            except Exception:
                return time_str

        readable_start = format_12h(start_time)
        readable_end = format_12h(end_time)

        await q.message.reply_text(
            f"⏳ *Work Window Closed!*\n"
            f"{DIVIDER}\n\n"
            f"Submission for *{task['task_name']}* is currently closed.\n\n"
            f"⏰ *Allowed Submission Time (Bangladesh Time):*\n"
            f"👉 **{readable_start} to {readable_end}**\n\n"
            f"Please submit your file within the scheduled time. Thank you! 🙏",
            parse_mode="Markdown"
        )
        return

    # ইউজারকে ফাইল পাঠানোর স্টেট এবং মেম্বার কাজের নাম সেভ করা
    user_states[user_id] = {
        "state": "waiting_for_file",
        "task_name": task["task_name"]
    }

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Submission", callback_data="cancel_submit")]])

    await q.message.reply_text(
        f"📁 *Submit File for: {task['task_name']}*\n"
        f"{DIVIDER}\n\n"
        f"✅ Please send your *.xlsx* file now.\n\n"
        f"📌 *Rules:*\n"
        f"  • Only *.xlsx / .xls* file formats are accepted\n"
        f"  • You can add a Caption with your file\n\n"
        f"_📎 Attach and send your file as a document_",
        parse_mode="Markdown",
        reply_markup=kb
    )


# ── Cancel submission callback handler ──
async def cb_cancel_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    user_states[user_id] = None # Reset State
    await q.message.reply_text("❌ _Submission cancelled successfully._", parse_mode="Markdown", reply_markup=MENU)


# ── My Submissions (Row to Dict Conversion) ─────────────────────────────
async def btn_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_status(update)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_status(update)

async def _show_status(update: Update):
    user = update.effective_user
    subs = db.get_user_submissions(user.id)

    if not subs:
        await update.message.reply_text(
            f"📭 *No submissions found.*\n\n"
            f"_Click '📁 Submit File' button to get started._",
            parse_mode="Markdown",
        )
        return

    total    = len(subs)
    approved = sum(1 for s in subs if s["status"] == "approved")
    pending  = sum(1 for s in subs if s["status"] == "pending")
    declined = sum(1 for s in subs if s["status"] == "declined")

    text = (
        f"📊 *My Submissions*\n"
        f"{DIVIDER}\n\n"
        f"📦 Total:        *{total}*\n"
        f"✅ Approved:     *{approved}*\n"
        f"⏳ Pending:      *{pending}*\n"
        f"❌ Declined:     *{declined}*\n\n"
        f"{DIVIDER}\n\n"
    )

    for sub in subs[:10]:
        sub_dict = dict(sub) # Row to Dict Conversion 
        em   = STATUS_EMOJI.get(sub_dict["status"], "❓")
        s_bn = STATUS_BN.get(sub_dict["status"], sub_dict["status"])
        task_info = f" ({sub_dict.get('task_name', 'General')})" if sub_dict.get('task_name') else ""
        text += (
            f"{em} *{sub_dict['sub_id']}*{task_info}\n"
            f"   📄 `{sub_dict['file_name']}`\n"
            f"   📅 {fmt_dt(sub_dict['submitted_at'])}\n"
            f"   📌 _{s_bn}_\n"
        )
        if sub_dict["admin_note"]:
            text += f"   💬 {sub_dict['admin_note']}\n"
        text += "\n"

    if total > 10:
        text += f"_...and {total - 10} more submissions are listed._"

    await update.message.reply_text(text, parse_mode="Markdown")


# ── My Payments ────────────────────────────────────────────────────────────────
async def btn_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_payments(update)

async def cmd_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_payments(update)

async def _show_payments(update: Update):
    user = update.effective_user
    pays = db.get_user_payments(user.id)

    if not pays:
        await update.message.reply_text(
            f"💰 *No payment records found.*\n\n"
            f"_Payments will be released after approval._",
            parse_mode="Markdown",
        )
        return

    total = sum(p["amount"] for p in pays)

    text = (
        f"💰 *My Payment History*\n"
        f"{DIVIDER}\n\n"
        f"📦 Total Payments: *{len(pays)}* times\n"
        f"💎 Total Received: *{total:,.0f} Taka*\n\n"
        f"{DIVIDER}\n\n"
    )

    for pay in pays[:10]:
        text += (
            f"💵 *{pay['pay_id']}*\n"
            f"   💲 *{pay['amount']:,.0f} Taka*\n"
            f"   📅 {fmt_dt(pay['sent_at'])}\n"
        )
        if pay["note"]:
            text += f"   📝 _{pay['note']}_\n"
        text += "\n"

    text += f"{DIVIDER}\n💎 *Grand Total: {total:,.0f} Taka*"
    await update.message.reply_text(text, parse_mode="Markdown")


# ── My Account (Row to Dict Conversion) ─────────────────────────────────
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
        f"〔 👤 *My Account* 〕\n"
        f"{DIVIDER}\n\n"

        f"🙍 *Name:*     {user.full_name}\n"
        f"🔗 *Username:* @{user.username or '—'}\n"
        f"🪪 *ID:*      `{user.id}`\n"
        f"📅 *Joined:*  {fmt_dt(db_user['registered_at'])}\n"
        f"🏅 *Badge:*   {badge}\n\n"

        f"{DIVIDER}\n\n"

        f"📊 *Submission Summary:*\n"
        f"  📦 Total:        *{total_s}*\n"
        f"  ✅ Approved:     *{approved}*\n"
        f"  ⏳ Pending:      *{pending}*\n"
        f"  ❌ Declined:     *{declined}*\n\n"
        f"  📈 Success Rate:\n"
        f"  {pbar(approved, total_s)} *{success}%*\n\n"
    )

    if last_sub:
        last_sub_dict = dict(last_sub) # Row to Dict Conversion 
        em = STATUS_EMOJI.get(last_sub_dict["status"], "❓")
        text += (
            f"  🕐 Latest Submission:\n"
            f"  {em} `{last_sub_dict['sub_id']}` — {fmt_dt(last_sub_dict['submitted_at'])}\n"
        )

    text += f"{DIVIDER}\n\n"

    text += (
        f"💰 *Payment Summary:*\n"
        f"  💵 Total Transactions: *{len(pays)}* times\n"
        f"  💎 Total Received:     *{total_p:,.0f} ৳*\n"
    )

    if last_pay:
        text += (
            f"  🕐 Latest Payment:\n"
            f"  💲 *{last_pay['amount']:,.0f} ৳* — {fmt_dt(last_pay['sent_at'])}\n"
        )

    text += f"\n{DIVIDER}"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Submissions", callback_data="acc_subs"),
            InlineKeyboardButton("💰 Payments",  callback_data="acc_pays"),
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
        await q.message.reply_text("📭 *No submissions found.*", parse_mode="Markdown"); return
    total    = len(subs)
    approved = sum(1 for s in subs if s["status"] == "approved")
    pending  = sum(1 for s in subs if s["status"] == "pending")
    declined = sum(1 for s in subs if s["status"] == "declined")
    text = (
        f"📊 *My Submissions*\n{DIVIDER}\n\n"
        f"📦 Total: *{total}*  ✅ *{approved}*  ⏳ *{pending}*  ❌ *{declined}*\n\n{DIVIDER}\n\n"
    )
    for sub in subs[:10]:
        sub_dict = dict(sub) # Row to Dict Conversion 
        em   = STATUS_EMOJI.get(sub_dict["status"], "❓")
        s_bn = STATUS_BN.get(sub_dict["status"], sub_dict["status"])
        task_info = f" ({sub_dict.get('task_name', 'General')})" if sub_dict.get('task_name') else ""
        text += f"{em} *{sub_dict['sub_id']}*{task_info}\n   📄 `{sub_dict['file_name']}`\n   📌 _{s_bn}_\n\n"
    await q.message.reply_text(text, parse_mode="Markdown")

async def _show_payments_from_query(q):
    user = q.from_user
    pays = db.get_user_payments(user.id)
    if not pays:
        await q.message.reply_text("💰 *No payment records found.*", parse_mode="Markdown"); return
    total = sum(p["amount"] for p in pays)
    text  = f"💰 *Payment History*\n{DIVIDER}\n\n"
    for pay in pays[:10]:
        text += f"💵 *{pay['pay_id']}*\n   💲 *{pay['amount']:,.0f} ৳*\n   📅 {fmt_dt(pay['sent_at'])}\n\n"
    text += f"{DIVIDER}\n💎 *Grand Total: {total:,.0f} ৳*"
    await q.message.reply_text(text, parse_mode="Markdown")


# ── Help ───────────────────────────────────────────────────────────────────────
async def btn_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_help(update)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_help(update)

async def _show_help(update: Update):
    await update.message.reply_text(
        f"ℹ️ *Help — {BOT_NAME}*\n"
        f"{DIVIDER}\n\n"
        f"*📁 File Submission Rules:*\n"
        f"  • Only *.xlsx / .xls* files are acceptable\n"
        f"  • Send as a 'File' on Telegram\n"
        f"  • You can add a Caption if needed\n\n"
        f"*📊 Status Meanings:*\n"
        f"  ⏳ Pending  → Admin hasn't reviewed yet\n"
        f"  ✅ Approved → Work accepted\n"
        f"  ❌ Declined → Work rejected\n\n"
        f"*🏅 Badge System:*\n"
        f"  🏆 Expert      → 90%+ success rate\n"
        f"  ⭐ Experienced → 70%+ success rate\n"
        f"  📈 Rising      → 40%+ success rate\n"
        f"  🌱 Beginner    → Newly joined member\n\n"
        f"*📌 Commands:*\n"
        f"  /start    — Main menu\n"
        f"  /account  — My account details\n"
        f"  /status   — Check submissions\n"
        f"  /payments — View payment history\n\n"
        f"{DIVIDER}\n"
        f"_Contact Admin for any further assistance._",
        parse_mode="Markdown",
    )


# ── File Handler ───────────────────────────────────────────────────────────────
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if not db.get_user(user_id):
        db.register_user(user_id, user.username, user.full_name)

    if not db.is_submissions_open():
        await update.message.reply_text(
            f"⚠️ *Submissions are Closed!*\n"
            f"{DIVIDER}\n\n"
            f"We are currently not accepting new file submissions at this time.\n\n"
            f"📢 _You will be notified once submissions are open again._\n"
            f"Thank you for your cooperation! 🙏",
            parse_mode="Markdown",
        )
        return

    # ইউজার কাজের ক্যাটাগরি সিলেক্ট করেছে কিনা চেক
    state = user_states.get(user_id)
    if not state or state.get("state") != "waiting_for_file":
        await update.message.reply_text(
            "⚠️ *Please select work type first!*\n\n"
            "Click the **📁 Submit File** button to choose your task before sending the file.",
            parse_mode="Markdown",
        )
        return

    doc   = update.message.document
    fname = doc.file_name or ""

    if not (fname.lower().endswith(".xlsx") or fname.lower().endswith(".xls")):
        await update.message.reply_text(
            f"❌ *Invalid file format!*\n\n"
            f"_Only_ `.xlsx` _or_ `.xls` _files are acceptable._",
            parse_mode="Markdown",
        )
        return

    proc    = await update.message.reply_text("⏳ _Processing file..._", parse_mode="Markdown")
    caption = update.message.caption or ""
    task_name = state.get("task_name", "General")
    
    sub_id  = db.add_submission(user_id, doc.file_id, fname, caption, task_name)
    await proc.delete()
    user_states[user_id] = None # Reset State

    await update.message.reply_text(
        f"〔 ✅ *Submission Successful!* 〕\n"
        f"{DIVIDER}\n\n"
        f"🆔 Tracking ID: `{sub_id}`\n"
        f"📂 Work Type: *{task_name}*\n"
        f"📄 File: `{fname}`\n"
        f"⏳ Status: *Pending*\n"
        f"🕐 Time: {fmt_dt(datetime.now().isoformat())}\n\n"
        f"_You will be notified once the admin reviews your file._\n"
        f"📊 Track your status with /status.",
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
                f"🔔 <b>New Submission!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"🆔 <code>{sub_id}</code>\n"
                f"📂 <b>Work Type:</b> <code>{task_name}</code>\n"
                f"👤 <b>{user.full_name}</b>\n"
                f"   🔗 @{user.username or '—'}\n"
                f"   🪪 <code>{user.id}</code>\n"
                f"📄 <code>{fname}</code>\n"
                f"💬 {caption or 'No caption'}\n"
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
        "❌ *Not as a Photo!*\n\n"
        "📎 _Please attach as a file:_\n"
        "`Attach → File → Select .xlsx`",
        parse_mode="Markdown",
    )


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    known = {
        "📁 Submit File", "📊 My Submissions",
        "💰 My Payments",  "👤 My Account",
        "ℹ️  Help",
    }
    if (update.message.text or "") not in known:
        await update.message.reply_text(
            "❓ _I did not understand._\n\n_Please use the menu below._",
            parse_mode="Markdown",
            reply_markup=MENU,
        )


# ── Text Button Dispatcher (Updated for English Buttons) ──────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Single handler for all text — dispatches by button label."""
    text = (update.message.text or "").strip()

    if text == "📁 Submit File":
        await btn_submit(update, context)
    elif text == "📊 My Submissions":
        await _show_status(update)
    elif text == "💰 My Payments":
        await _show_payments(update)
    elif text == "👤 My Account":
        await _show_account(update)
    elif "Help" in text:
        await _show_help(update)
    else:
        await update.message.reply_text(
            "❓ _I did not understand._\n\n_Please use the menu below._",
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

    # Inline buttons callbacks
    app.add_handler(CallbackQueryHandler(cb_account, pattern=r"^acc_"))
    app.add_handler(CallbackQueryHandler(cb_select_task, pattern=r"^seltask_")) 
    app.add_handler(CallbackQueryHandler(cb_cancel_submit, pattern=r"^cancel_submit$")) 

    return app
