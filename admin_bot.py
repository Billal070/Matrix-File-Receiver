import logging, os, io, html, sys, telegram
from datetime import datetime, timedelta
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
import database as db
from config import ADMIN_BOT_TOKEN, USER_BOT_TOKEN, ADMIN_TELEGRAM_ID, BOT_NAME, DIVIDER

logger = logging.getLogger(__name__)
SELECT_USER, ENTER_AMOUNT, ENTER_NOTE, ATTACH_FILE = range(4)
ENTER_TASK_NAME = range(5, 6)
BROADCAST_TEXT = 10
STATUS_EMOJI = {"pending": "⏳", "approved": "✅", "declined": "❌"}

# ── 4 Primary Reply Keyboard Buttons for Admin ───────────────────────────────
ADMIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Dashboard"), KeyboardButton("📈 Analytics")],
        [KeyboardButton("💳 Payments"), KeyboardButton("⚙️ Settings")]
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# ── Dynamic Premium Emojis Mapping ───────────────────────────────────────────
CUSTOM_EMOJIS = {
    "💎": '<tg-emoji emoji-id="5427168083074628963">💎</tg-emoji>', "📊": '<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji>',
    "💵": '<tg-emoji emoji-id="5409048419211682843">💵</tg-emoji>', "❓": '<tg-emoji emoji-id="5436113877181941026">❓</tg-emoji>',
    "✔️": '<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji>', "💬": '<tg-emoji emoji-id="5443038326535759644">💬</tg-emoji>',
    "❌": '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji>', "💰": '<tg-emoji emoji-id="6235459831302460476">💰</tg-emoji>',
    "🔜": '<tg-emoji emoji-id="5440621591387980068">🔜</tg-emoji>', "⚠️": '<tg-emoji emoji-id="5447644880824181073">⚠️</tg-emoji>',
    "🌐": '<tg-emoji emoji-id="5447410659077661506">🌐</tg-emoji>', "⛔️": '<tg-emoji emoji-id="5260293700088511294">⛔️</tg-emoji>',
    "🔔": '<tg-emoji emoji-id="5458603043203327669">🔔</tg-emoji>', "✉️": '<tg-emoji emoji-id="5253742260054409879">✉️</tg-emoji>',
    "🔒": '<tg-emoji emoji-id="5296369303661067030">🔒</tg-emoji>', "⚙️": '<tg-emoji emoji-id="5895577117592128901">⚙️</tg-emoji>',
    "🤔": '<tg-emoji emoji-id="5210729536974503652">🤔</tg-emoji>', "on": '<tg-emoji emoji-id="5210881166499921911">🔓</tg-emoji>',
    "off": '<tg-emoji emoji-id="5208840468623801290">🔒</tg-emoji>', "🗓": '<tg-emoji emoji-id="5413879192267805083">🗓</tg-emoji>',
    "⭐️": '<tg-emoji emoji-id="5438496463044752972">⭐️</tg-emoji>', "👀": '<tg-emoji emoji-id="5210956306952758910">👀</tg-emoji>',
    "⚡️": '<tg-emoji emoji-id="5456140674028019486">⚡️</tg-emoji>', "📌": '<tg-emoji emoji-id="5397782960512444700">📌</tg-emoji>',
    "🖥": '<tg-emoji emoji-id="5282843764451195532">🖥</tg-emoji>'
}

def em(key): return CUSTOM_EMOJIS.get(key, key)

def is_admin(uid):
    try: return int(uid) == int(ADMIN_TELEGRAM_ID)
    except: return str(uid) == str(ADMIN_TELEGRAM_ID)

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{em('📌')} <b>Telegram ID:</b>\n<code>{update.effective_user.id}</code>\n\n_Railway variable: ADMIN_TELEGRAM_ID_", parse_mode="HTML")

def fmt_dt(s):
    from datetime import datetime
    try: return datetime.fromisoformat(s).strftime("%d %b %Y  %I:%M %p")
    except: return s or "N/A"

def pbar(val, total, w=8):
    if total == 0: return "░" * w
    f = round(val / total * w)
    return "█" * f + "░" * (w - f)

def pct(val, total): return round(val / total * 100) if total else 0


# Admin Menu Keyboard with "Manage Works" option
def _dashboard_keyboard():
    is_open = db.is_submissions_open()
    status_btn = InlineKeyboardButton("🔒 Close Submissions" if is_open else "🔓 Open Submissions", callback_data="nav_toggle_subs")
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ Pending", callback_data="nav_pending"), InlineKeyboardButton("📋 History", callback_data="nav_history")],
        [InlineKeyboardButton("👥 Members", callback_data="nav_members"), InlineKeyboardButton("💰 Payments", callback_data="nav_payments")],
        [InlineKeyboardButton("📊 Stats", callback_data="nav_stats"), InlineKeyboardButton("📣 Broadcast", callback_data="nav_broadcast")],
        [InlineKeyboardButton("💸 Send Payment", callback_data="nav_sendpayment")],
        [InlineKeyboardButton("🛠️ Manage Works", callback_data="nav_manage_tasks")], # Manage Tasks Button
        [status_btn]
    ])


def _build_dashboard_text(stats):
    alert = f"\n{em('🔔')} <b>{stats['pending']} Pending!</b>" if stats["pending"] else ""
    t = stats["total_subs"]
    is_open = db.is_submissions_open()
    status_text = "🟢 OPEN" if is_open else "🔴 CLOSED"
    
    return (
        f"〔 👨‍💼 <b>Admin Panel</b> 〕\n🔷 {BOT_NAME}\n{DIVIDER}{alert}\n\n"
        f"📂 Submission Window: <b>{status_text}</b>\n\n"
        f"{em('📊')} <b>Stats:</b>\n  👥 Members:      <b>{stats['total_users']}</b> users\n  📁 Submissions:  <b>{t}</b> files\n\n"
        f"  ✅ Approved: {pbar(stats['approved'],t)} <b>{stats['approved']}</b> ({pct(stats['approved'],t)}%)\n"
        f"  ⏳ Pending:  {pbar(stats['pending'],t)} <b>{stats['pending']}</b> ({pct(stats['pending'],t)}%)\n"
        f"  ❌ Declined: {pbar(stats['declined'],t)} <b>{stats['declined']}</b> ({pct(stats['declined'],t)}%)\n\n"
        f"  {em('💰')} Total Paid: <b>{stats['total_paid']:,.0f} ৳</b>\n{DIVIDER}\n_Select any option_ 👇"
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(f"{em('⛔️')} <b>Unauthorized!</b>\n\nID: <code>{update.effective_user.id}</code>", parse_mode="HTML")
        return
    await update.message.reply_text(_build_dashboard_text(db.get_stats()), parse_mode="HTML", reply_markup=ADMIN_MENU)


async def cb_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Unauthorized", show_alert=True); return
    await q.answer()
    if q.data == "nav_pending": await _send_pending(q.message.chat_id, context)
    elif q.data == "nav_history": await _send_history_paginated(q.message.chat_id, context, offset=0, edit=True, q=q)
    elif q.data == "nav_members": await _send_members(q.message.chat_id, context)
    elif q.data == "nav_payments": await _send_payments(q.message.chat_id, context)
    elif q.data == "nav_stats": await _send_stats(q.message.chat_id, context)
    elif q.data == "nav_done":
        pass
    
    # ── Manage Tasks View Handler ──
    elif q.data == "nav_manage_tasks" or q.data == "nav_back_tasks":
        await _show_manage_tasks_menu(q.message.chat_id, context)
        
    elif q.data == "nav_back_dashboard":
        stats = db.get_stats()
        await q.edit_message_text(_build_dashboard_text(stats), parse_mode="HTML", reply_markup=_dashboard_keyboard())

    # Submissions settings page toggle (Returns back to settings page)
    elif q.data == "nav_toggle_subs_settings":
        current_status = db.is_submissions_open()
        new_status = not current_status
        db.set_submissions_open(new_status)
        
        status_word = "OPENED" if new_status else "CLOSED"
        await q.answer(f"📂 Submissions are now {status_word}!", show_alert=True)
        
        status_btn = InlineKeyboardButton("🔒 Close Submissions" if new_status else "🔓 Open Submissions", callback_data="nav_toggle_subs_settings")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠️ Manage Works", callback_data="nav_manage_tasks")],
            [InlineKeyboardButton("👥 Members", callback_data="nav_members")],
            [status_btn],
            [InlineKeyboardButton("◀️ Back to Dashboard", callback_data="nav_back_dashboard")]
        ])
        await q.edit_message_text("〔 ⚙️ <b>Settings & Configuration</b> 〕\n" + DIVIDER + "\n\nAdjust your bot's operation parameters:", parse_mode="HTML", reply_markup=kb)


# Manage Tasks Menu Helper (OperationalError Removed)
async def _show_manage_tasks_menu(chat_id, context):
    db_conn = db._conn()
    unique_tasks_rows = db_conn.execute("SELECT id, task_name FROM tasks").fetchall()
    db_conn.close()

    text = f"{em('⚙️')} <b>Manage Work Types</b>\n{DIVIDER}\n\n"
    if not unique_tasks_rows:
        text += "⚠️ No custom work types set. Users can't submit files right now!\n\n_Click '+ Add New Work' button below to create one._"
    else:
        text += f"{em('📌')} <b>Current Active Works:</b>\n"
        for i, t in enumerate(unique_tasks_rows, 1):
            text += f"   {i}. <b>{t['task_name']}</b>\n"
        text += "\n_Click trash icon next to a work below to delete it._"

    kb_buttons = []
    for t in unique_tasks_rows:
        kb_buttons.append([
            InlineKeyboardButton(f"📄 {t['task_name']}", callback_data="nav_done"),
            InlineKeyboardButton("❌ Delete", callback_data=f"deltask_{t['id']}")
        ])
    kb_buttons.append([InlineKeyboardButton("➕ Add New Work", callback_data="add_task_init")])
    kb_buttons.append([InlineKeyboardButton("◀️ Back to Dashboard", callback_data="nav_back_dashboard")])

    await context.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb_buttons))


# Delete Task Callback
async def cb_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id): await q.answer("⛔"); return
    await q.answer()

    task_id = int(q.data.replace("deltask_", ""))
    task = db.get_task_by_id(task_id)
    if task:
        db.delete_task(task_id)
        await q.message.reply_text(f"🗑️ Work type **'{task['task_name']}'** has been deleted!", parse_mode="Markdown")
    
    # Refresh menu
    await _show_manage_tasks_menu(q.message.chat_id, context)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_stats(update.message.chat_id, context)

# Back to dashboard button added
async def _send_stats(chat_id, context):
    s = db.get_stats()
    t = s["total_subs"]
    text = (
        f"{em('📊')} <b>Detailed Statistics</b>\n{DIVIDER}\n\n👥 <b>Members:</b> <b>{s['total_users']}</b> active\n\n"
        f"📁 <b>Submissions:</b> <b>{t}</b>\n"
        f"   ✅ Approved: <b>{s['approved']}</b>  {pbar(s['approved'],t)} {pct(s['approved'],t)}%\n"
        f"   ⏳ Pending:  <b>{s['pending']}</b>  {pbar(s['pending'],t)} {pct(s['pending'],t)}%\n"
        f"   ❌ Declined: <b>{s['declined']}</b>  {pbar(s['declined'],t)} {pct(s['declined'],t)}%\n\n"
        f"{em('💰')} <b>Payments:</b> <b>{s['total_payments']}</b> times\n   Total Paid: <b>{s['total_paid']:,.0f} ৳</b>\n\n{DIVIDER}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Dashboard", callback_data="nav_back_dashboard")]])
    await context.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_pending(update.message.chat_id, context)

# sqlite3.Row object get method bypass
async def _send_pending(chat_id, context):
    subs = db.get_pending_submissions()
    if not subs:
        await context.bot.send_message(chat_id, "✅ *No Pending Submissions Found!*", parse_mode="Markdown"); return
    await context.bot.send_message(chat_id, f"{em('⏳')} <b>{len(subs)} Pending Submissions</b>", parse_mode="HTML")
    for sub in subs[:6]:
        sub_dict = dict(sub) # Row to Dict Conversion 
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅  Approve", callback_data=f"approve_{sub_dict['sub_id']}"), InlineKeyboardButton("❌  Decline", callback_data=f"decline_{sub_dict['sub_id']}")]])
        
        # HTML characters escaping to ensure robustness
        safe_sub_id = html.escape(str(sub_dict['sub_id']))
        safe_task = html.escape(str(sub_dict.get('task_name', 'General')))
        safe_name = html.escape(str(sub_dict['full_name']))
        safe_user = html.escape(str(sub_dict['username'] or '—'))
        safe_fname = html.escape(str(sub_dict['file_name']))
        safe_caption = html.escape(str(sub_dict['caption'] or 'No caption'))
        
        cap = (
            f"📨 <b>{safe_sub_id}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📂 <b>Work Type:</b> <code>{safe_task}</code>\n"
            f"👤 <b>{safe_name}</b> (@{safe_user})\n"
            f"📄 <code>{safe_fname}</code>\n"
            f"💬 {safe_caption}\n"
            f"📅 {fmt_dt(sub_dict['submitted_at'])}"
        )
        try: await context.bot.send_document(chat_id=chat_id, document=sub_dict["file_id"], caption=cap, parse_mode="HTML", reply_markup=kb)
        except Exception as e: logger.error(f"Doc send error: {e}")

     # FIXED: Paginated 7-Days Submission History with robust HTML escaping
async def _send_history_paginated(chat_id, context, offset=0, edit=False, q=None):
    from datetime import datetime, timedelta # Local safe imports
    limit = 5
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    
    db_conn = db._conn()
    total_count = db_conn.execute("""
        SELECT COUNT(*) 
        FROM submissions s
        JOIN users u ON s.user_id = u.user_id
        WHERE s.submitted_at >= ?
    """, (seven_days_ago,)).fetchone()[0]
    
    subs = db_conn.execute("""
        SELECT s.*, u.username, u.full_name
        FROM submissions s
        JOIN users u ON s.user_id = u.user_id
        WHERE s.submitted_at >= ?
        ORDER BY s.submitted_at DESC
        LIMIT ? OFFSET ?
    """, (seven_days_ago, limit, offset)).fetchall()
    db_conn.close()
    
    if not subs and offset == 0:
        msg_text = "📭 *No submissions found in the last 7 days.*"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Dashboard", callback_data="nav_back_dashboard")]])
        if edit and q: await q.edit_message_text(msg_text, parse_mode="Markdown", reply_markup=kb)
        else: await context.bot.send_message(chat_id, msg_text, parse_mode="Markdown", reply_markup=kb)
        return

    text = f"{em('📋')} <b>Submission History (Last 7 Days)</b>\n<i>Page {offset//limit + 1}</i>\n{DIVIDER}\n\n"
    
    for sub in subs:
        sub_dict = dict(sub)
        em_indicator = STATUS_EMOJI.get(sub_dict["status"], "❓")
        formatted_time = fmt_dt(sub_dict["submitted_at"])
        
        # HTML Characters Escaping for each row
        safe_sub_id = html.escape(str(sub_dict['sub_id']))
        safe_status = html.escape(str(sub_dict['status'].upper()))
        safe_task = html.escape(str(sub_dict.get('task_name', 'General')))
        safe_name = html.escape(str(sub_dict['full_name']))
        safe_user = html.escape(str(sub_dict['username'] or '—'))
        safe_fname = html.escape(str(sub_dict['file_name']))
        
        text += (
            f"{em_indicator} <b>{safe_sub_id}</b> — <i>{safe_status}</i>\n"
            f"   📂 <b>Work:</b> <code>{safe_task}</code>\n"
            f"   👤 <b>User:</b> {safe_name} (@{safe_user})\n"
            f"   🪪 <b>Chat ID:</b> <code>{sub_dict['user_id']}</code>\n"
            f"   📄 <b>File:</b> <code>{safe_fname}</code>\n"
            f"   📅 <b>Date/Time:</b> {formatted_time}\n\n"
        )
        
    kb_buttons = []
    navigation_row = []
    if offset > 0:
        navigation_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"nav_subhist_{offset - limit}"))
    if total_count > (offset + limit):
        navigation_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"nav_subhist_{offset + limit}"))
        
    if navigation_row:
        kb_buttons.append(navigation_row)
        
    kb_buttons.append([InlineKeyboardButton("◀️ Back to Dashboard", callback_data="nav_back_dashboard")])
    reply_markup = InlineKeyboardMarkup(kb_buttons)
    
    if edit and q:
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)


# Pagination callback handler for submission history
async def cb_subhist_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    offset = int(q.data.replace("nav_subhist_", ""))
    await _send_history_paginated(q.message.chat_id, context, offset=offset, edit=True, q=q)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_history_paginated(update.message.chat_id, context, offset=0)


async def cmd_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_members(update.message.chat_id, context)

# Back to dashboard button added (FIXED: HTML escaping added)
async def _send_members(chat_id, context):
    users = db.get_all_users()
    if not users:
        await context.bot.send_message(chat_id, "👥 *No members found.*", parse_mode="Markdown"); return
    text = f"👥 <b>All Members ({len(users)} total)</b>\n{DIVIDER}\n\n"
    keyboard = []
    for i, u in enumerate(users, 1):
        ms = db.get_member_stats(u["user_id"])
        
        safe_name = html.escape(str(u['full_name']))
        safe_user = html.escape(str(u['username'] or '—'))
        
        text += f"<b>{i}. {safe_name}</b> (@{safe_user})\n   📁 {len(ms['subs'])} Subs | 💰 <b>{ms['total_paid']:,.0f} ৳</b>\n\n"
        keyboard.append([InlineKeyboardButton(f"👤 {u['full_name']}", callback_data=f"member_{u['user_id']}")])
    keyboard.append([InlineKeyboardButton("◀️ Back to Dashboard", callback_data="nav_back_dashboard")]) # Back Button
    await context.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# Back buttons added (FIXED: HTML escaping added)
async def cb_member_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id): await q.answer("⛔", show_alert=True); return
    await q.answer()
    uid = int(q.data.replace("member_", ""))
    user = db.get_user(uid)
    if not user: await q.message.reply_text("❌ Member not found."); return
    ms = db.get_member_stats(uid)
    
    safe_name = html.escape(str(user['full_name']))
    safe_user = html.escape(str(user['username'] or '—'))
    
    text = (f"👤 <b>{safe_name}</b> (@{safe_user})\n{DIVIDER}\n\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📅 Joined: {fmt_dt(user['registered_at'])}\n\n"
            f"📁 <b>Submissions:</b> Total {len(ms['subs'])} (✅ {ms['approved']} ⏳ {ms['pending']} ❌ {ms['declined']})\n"
            f"💰 <b>Payments:</b> Total {ms['total_paid']:,.0f} ৳\n\n")
    if ms["subs"]:
        text += "📋 <b>Latest Submissions:</b>\n"
        for sub in ms["subs"][:5]:
            sub_dict = dict(sub)
            em_indicator = STATUS_EMOJI.get(sub_dict["status"], "❓")
            text += f"   {em_indicator} <code>{sub_dict['sub_id']}</code> — {fmt_dt(sub_dict['submitted_at'])}\n"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💸 Send Payment", callback_data=f"quickpay_{uid}")],
        [InlineKeyboardButton("◀️ Back to Members", callback_data="nav_members"), InlineKeyboardButton("◀️ Back to Dashboard", callback_data="nav_back_dashboard")]
    ])
    await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

async def cmd_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_payments(update.message.chat_id, context)

# Back to dashboard button added
async def _send_payments(chat_id, context):
    pays = db.get_all_payments(limit=20)
    if not pays:
        await context.bot.send_message(chat_id, "💰 *No payment history found.*", parse_mode="Markdown"); return
    total = sum(p["amount"] for p in pays)
    text = f"{em('💰')} <b>Payment History</b>\n{DIVIDER}\n\n"
    for pay in pays:
        text += f"{em('💵')} <b>{pay['pay_id']}</b>\n   👤 {pay['full_name']}\n   💲 <b>{pay['amount']:,.0f} ৳</b> — {fmt_dt(pay['sent_at'])}\n\n"
    text += f"{DIVIDER}\n{em('💎')} <b>Grand Total: {total:,.0f} ৳</b>"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Dashboard", callback_data="nav_back_dashboard")]])
    await context.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)


# Paid Who (Paginated list of paid users with inline details button - FIXED: HTML escaping added)
async def cb_paid_who(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    offset = 0
    if q.data.startswith("nav_paidwho_"):
        offset = int(q.data.replace("nav_paidwho_", ""))
        
    limit = 5
    db_conn = db._conn()
    pays = db_conn.execute("""
        SELECT p.*, u.username, u.full_name 
        FROM payments p JOIN users u ON p.user_id = u.user_id
        ORDER BY p.sent_at DESC LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    
    # Check if there are more items to paginate
    has_more = db_conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] > (offset + limit)
    db_conn.close()
    
    if not pays and offset == 0:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Dashboard", callback_data="nav_back_dashboard")]])
        await q.edit_message_text("❌ No payment records found.", reply_markup=kb)
        return
        
    text = f"👥 <b>Paid Members List</b> (Page {offset//limit + 1})\n{DIVIDER}\n\n"
    kb_buttons = []
    
    for p in pays:
        safe_name = html.escape(str(p['full_name']))
        safe_pay_id = html.escape(str(p['pay_id']))
        text += f"{em('💵')} <b>{safe_pay_id}</b> | {safe_name} | <b>{p['amount']:,.0f} ৳</b>\n📅 {fmt_dt(p['sent_at'])}\n\n"
        kb_buttons.append([InlineKeyboardButton(f"👤 Detail: {p['full_name']}", callback_data=f"member_{p['user_id']}")])
        
    navigation_row = []
    if offset > 0:
        navigation_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"nav_paidwho_{offset - limit}"))
    if has_more:
        navigation_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"nav_paidwho_{offset + limit}"))
        
    if navigation_row:
        kb_buttons.append(navigation_row)
        
    kb_buttons.append([InlineKeyboardButton("◀️ Back to Dashboard", callback_data="nav_back_dashboard")])
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb_buttons))


# ── Payment Flow ──────────────────────────────────────────────────────────────

async def _sendpayment_init(chat_id, context):
    """Show member selection list."""
    users = db.get_all_users()
    if not users:
        await context.bot.send_message(chat_id, "👥 _No members found._", parse_mode="Markdown"); return False
    context.user_data["pay_users"] = {str(u["user_id"]): dict(u) for u in users}
    kb = []
    for u in users:
        total = sum(p["amount"] for p in db.get_user_payments(u["user_id"]))
        kb.append([InlineKeyboardButton(f"👤 {u['full_name']} ({total:,.0f} ৳)", callback_data=f"payto_{u['user_id']}")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="pay_cancel")])
    await context.bot.send_message(chat_id, f"💸 *Send Payment*\n{DIVIDER}\n\nSelect a member to send payment to:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return True

# Entry point: /sendpayment command
async def cmd_sendpayment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    ok = await _sendpayment_init(update.message.chat_id, context)
    return SELECT_USER if ok else ConversationHandler.END

# Entry point: Dashboard button "💸 পেমেন্ট পাঠান"
async def cb_nav_sendpayment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔", show_alert=True); return ConversationHandler.END
    await q.answer()
    ok = await _sendpayment_init(q.message.chat_id, context)
    return SELECT_USER if ok else ConversationHandler.END

# Entry point: Member detail "💸 পেমেন্ট পাঠান" button
async def cb_quickpay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id): await q.answer("⛔", show_alert=True); return ConversationHandler.END
    await q.answer()
    uid = int(q.data.replace("quickpay_", ""))
    user = db.get_user(uid)
    users = db.get_all_users()
    context.user_data["pay_users"] = {str(u["user_id"]): dict(u) for u in users}
    context.user_data["pay_uid"] = uid
    context.user_data["pay_name"] = user["full_name"] if user else str(uid)
    
    # Inline Cancel button added under money input
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pay_cancel")]])
    await q.message.reply_text(
        f"Selected: *{context.user_data['pay_name']}*\n\n💲 *Enter the amount to send:* (Digits only, e.g. 5000)",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return ENTER_AMOUNT

# Select user cancel inline handler
async def cb_select_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "pay_cancel":
        await q.edit_message_text("❌ _Payment cancelled._", parse_mode="Markdown"); return ConversationHandler.END
    uid_str = q.data.replace("payto_", "")
    sel = context.user_data.get("pay_users", {}).get(uid_str)
    if not sel: await q.edit_message_text("❌ Error."); return ConversationHandler.END
    context.user_data["pay_uid"] = int(uid_str)
    context.user_data["pay_name"] = sel["full_name"]
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pay_cancel")]])
    await q.edit_message_text(
        f"✅ Selected: *{sel['full_name']}*\n\n💲 *How much to send?*",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return ENTER_AMOUNT

# Inline Cancel button added
async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().replace(",", "").replace("৳", "").replace(" ", "")
    try:
        amount = float(raw)
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ *Please enter a valid amount.*\n_Example: 5000_", parse_mode="Markdown")
        return ENTER_AMOUNT
    context.user_data["pay_amount"] = amount
    
    # Skip and Cancel buttons in line
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ Skip Note", callback_data="note_skip")],
        [InlineKeyboardButton("❌ Cancel", callback_data="pay_cancel")]
    ])
    await update.message.reply_text(
        f"💲 Amount: *{amount:,.0f} ৳* ✅\n\n📝 *Do you want to add a note?*\n_(bKash number, Nagad reference, etc.)_",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return ENTER_NOTE

# Skip and Cancel buttons in line
async def cb_note_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["pay_note"] = ""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ Skip File", callback_data="file_skip")],
        [InlineKeyboardButton("❌ Cancel", callback_data="pay_cancel")]
    ])
    await q.edit_message_text(
        f"💲 *{context.user_data['pay_amount']:,.0f} ৳* | 📝 Note: _None_\n\n📎 *Send a file/receipt or click skip.*",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return ATTACH_FILE

# Skip and Cancel buttons in line
async def enter_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pay_note"] = update.message.text.strip()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ Skip File", callback_data="file_skip")],
        [InlineKeyboardButton("❌ Cancel", callback_data="pay_cancel")]
    ])
    await update.message.reply_text(
        f"💲 *{context.user_data['pay_amount']:,.0f} ৳* | 📝 _{context.user_data['pay_note']}_\n\n📎 *Send a file/receipt or click skip.*",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return ATTACH_FILE

async def attach_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fid, fname = None, "receipt"
    if update.message.document:
        fid = update.message.document.file_id
        fname = update.message.document.file_name or "document"
    elif update.message.photo:
        fid = update.message.photo[-1].file_id
        fname = "receipt.jpg"
    context.user_data["pay_file"] = fid
    context.user_data["pay_filename"] = fname
    await _finalize_payment(update, context)
    return ConversationHandler.END

async def cmd_skip_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pay_file"] = None
    await _finalize_payment(update, context)
    return ConversationHandler.END

# Inline file skip handler
async def cb_skip_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["pay_file"] = None
    await _finalize_payment(q, context)
    return ConversationHandler.END

async def cmd_cancel_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ _Payment cancelled._", parse_mode="Markdown")
    return ConversationHandler.END

# Universal Inline cancel callback handler for payments
async def cb_cancel_pay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data.clear()
    await q.edit_message_text("❌ _Payment cancelled successfully._")
    return ConversationHandler.END

# Updated context message sender helper (using Local datetime import)
async def _finalize_payment(update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime  # Local Import
    uid, name = context.user_data["pay_uid"], context.user_data["pay_name"]
    amount, note = context.user_data["pay_amount"], context.user_data.get("pay_note", "")
    fid = context.user_data.get("pay_file")
    fname = context.user_data.get("pay_filename", "receipt")
    pay_id = db.add_payment(uid, amount, note, fid)
    user_text = f"〔 {em('💰')} <b>Payment Notification!</b> 〕\n{DIVIDER}\n\n🆔 ID: <code>{pay_id}</code>\n💵 Amount: <b>{amount:,.0f} ৳</b>\n"
    if note: user_text += f"📝 Details: _{note}_\n"
    user_text += f"📅 Date: {fmt_dt(datetime.now().isoformat())}\n\nThank you! 🙏"
    try:
        async with Bot(token=USER_BOT_TOKEN) as user_bot:
            if fid:
                file_obj = await context.bot.get_file(fid)
                file_bytes = await file_obj.download_as_bytearray()
                file_io = io.BytesIO(file_bytes)
                file_io.name = fname
                await user_bot.send_document(chat_id=uid, document=file_io, caption=user_text, parse_mode="Markdown")
            else:
                await user_bot.send_message(chat_id=uid, text=user_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Payment notify failed: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ Payment saved but failed to notify user!\nError: {e}")
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"〔 ✅ *Payment Sent Successfully!* 〕\n{DIVIDER}\n\n🆔 {pay_id}\n👤 *{name}*\n💲 *{amount:,.0f} ৳*",
        parse_mode="Markdown"
    )
    context.user_data.clear()

# ── Broadcast ─────────────────────────────────────────────────────────────────

# Broadcast entry point from CallbackQuery
async def cb_nav_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔", show_alert=True)
        return ConversationHandler.END
    await q.answer()
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="bc_cancel")]])
    await q.message.reply_text(
        f"{em('📣')} <b>Broadcast</b>\n{DIVIDER}\n\n"
        f"Please write the broadcast message you want to send to all members:\n\n"
        f"_Press Cancel button below to abort._",
        parse_mode="HTML",
        reply_markup=kb
    )
    return BROADCAST_TEXT

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="bc_cancel")]])
    await update.message.reply_text(f"📣 *Broadcast*\n{DIVIDER}\n\nWrite broadcast message:\n_Press Cancel to abort._", parse_mode="Markdown", reply_markup=kb)
    return BROADCAST_TEXT

# Updated broadcast helper with Local datetime import
async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime  # Local Import
    msg = update.message.text.strip()
    users = db.get_all_users()
    if not users: await update.message.reply_text("👥 No members found."); return ConversationHandler.END
    proc = await update.message.reply_text("📣 _Broadcasting..._", parse_mode="Markdown")
    success, failed = 0, 0
    broadcast_text = f"{em('📣')} <b>Matrix File Receiver</b>\n{DIVIDER}\n\n{msg}\n\n_{fmt_dt(datetime.now().isoformat())}_"
    try:
        async with Bot(token=USER_BOT_TOKEN) as user_bot:
            for u in users:
                try:
                    await user_bot.send_message(chat_id=u["user_id"], text=broadcast_text, parse_mode="HTML")
                    success += 1
                except: failed += 1
    except Exception as e: logger.error(f"Broadcast failed: {e}")
    await proc.delete()
    await update.message.reply_text(f"✅ *Broadcast Completed!*\n\n✅ Success: {success}\n❌ Failed: {failed}", parse_mode="Markdown")
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ _Cancelled._", parse_mode="Markdown"); return ConversationHandler.END

# Inline broadcast cancel callback handler
async def cb_cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("❌ _Broadcast cancelled successfully._")
    return ConversationHandler.END

# ── Manage Tasks (Conversation handlers) ──────────────────────────────────────
async def cb_add_task_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id): await q.answer("⛔"); return ConversationHandler.END
    await q.answer()
    
    # Cancel button added
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="task_cancel")]])
    await q.message.reply_text(
        f"📝 *Add New Work Type*\n{DIVIDER}\n\n"
        f"Please enter the name of the new task/work type:\n"
        f"_(e.g., Lead Generation, YouTube Review, Data Entry)_",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return ENTER_TASK_NAME

async def enter_task_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_name = update.message.text.strip()
    if not task_name:
        await update.message.reply_text("❌ Work name cannot be empty. Please enter again:")
        return ENTER_TASK_NAME

    success = db.add_task(task_name)
    if success:
        await update.message.reply_text(f"✅ Work type **'{task_name}'** has been added successfully!", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ This work type name already exists! Please try again:")
        return ENTER_TASK_NAME
    
    await _show_manage_tasks_menu(update.message.chat_id, context)
    return ConversationHandler.END

async def cmd_cancel_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ _Cancelled task adding._", parse_mode="Markdown")
    await _show_manage_tasks_menu(update.message.chat_id, context)
    return ConversationHandler.END

# Inline task cancel handler
async def cb_cancel_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("❌ _Task creation cancelled._")
    await _show_manage_tasks_menu(q.message.chat_id, context)
    return ConversationHandler.END


# ── Approve / Decline (Updated with Local datetime import & Dict Conversion) ──
async def cb_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime  # Local Import
    q = update.callback_query
    if not is_admin(q.from_user.id): await q.answer("⛔ Unauthorized!", show_alert=True); return
    action, sub_id = q.data.split("_", 1)
    sub = db.get_submission(sub_id)
    if not sub: await q.answer("❌ Submission not found!", show_alert=True); return
    
    sub_dict = dict(sub) # Row to Dict Conversion
    if sub_dict["status"] != "pending": await q.answer(f"⚠️ Already {sub_dict['status'].upper()}!", show_alert=True); return
    now = fmt_dt(datetime.now().isoformat())
    if action == "approve":
        db.update_submission_status(sub_id, "approved")
        user_msg = f"〔 🎉 *File Approved!* 〕\n{DIVIDER}\n\n🆔 ID: `{sub_id}`\n📄 `{sub_dict['file_name']}`\n✅ *Approved*\n\nThank you 🙏"
        result_line = f"\n━━━━━━━━━━━━━━━━━━\n{em('✔️')} <b>APPROVED</b> — {now}"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Approved ✅", callback_data="nav_done")]])
        await q.answer("✅ Approved!")
    else:
        db.update_submission_status(sub_id, "declined")
        user_msg = f"〔 ❌ *File Declined!* 〕\n{DIVIDER}\n\n🆔 ID: `{sub_id}`\n📄 `{sub_dict['file_name']}`\n❌ *Declined*"
        result_line = f"\n━━━━━━━━━━━━━━━━━━\n{em('❌')} <b>DECLINED</b> — {now}"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Declined ❌", callback_data="nav_done")]])
        await q.answer("❌ Declined!")
    try:
        async with Bot(token=USER_BOT_TOKEN) as user_bot:
            await user_bot.send_message(chat_id=sub_dict["user_id"], text=user_msg, parse_mode="Markdown")
    except Exception as e: logger.error(f"Notify failed: {e}")
    try:
        new_cap = (q.message.caption_html or "") + result_line
        await q.edit_message_caption(caption=new_cap, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"Caption edit failed: {e}")
        try: await q.edit_message_reply_markup(reply_markup=reply_markup)
        except Exception as ex: logger.error(f"Markup edit failed: {ex}")

# ── Debug / Emoji Test (FIXED: Official tg-emoji parsing test added) ────────
async def cmd_testnotify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; await update.message.reply_text("🔍 Testing... wait.")
    is_match = str(uid) == str(ADMIN_TELEGRAM_ID)
    info = f"📋 <b>Check:</b>\nID: <code>{uid}</code>\nADMIN_TELEGRAM_ID: <code>{ADMIN_TELEGRAM_ID}</code>\nMatch: {is_match}"
    await update.message.reply_text(info, parse_mode="HTML")
    
    # Premium Emoji Rendering Test Line Added
    await update.message.reply_text(
        '💎 <b>Premium Emoji Render Test:</b>\n'
        '<tg-emoji emoji-id="5427168083074628963">💎</tg-emoji> Matrix File Receiver',
        parse_mode="HTML"
    )
    
    try:
        async with Bot(token=USER_BOT_TOKEN) as test_bot:
            bot_info = await test_bot.get_me()
            await update.message.reply_text(f"✅ USER_BOT: <b>{bot_info.full_name}</b>", parse_mode="HTML")
            try:
                await test_bot.send_message(chat_id=ADMIN_TELEGRAM_ID, text="✅ Test notification working!")
                await update.message.reply_text("✅ Notification sent successfully!")
            except Exception as e:
                await update.message.reply_text(f"❌ Send error:\n<code>{e}</code>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Token error:\n<code>{e}</code>", parse_mode="HTML")


# ── New /testemoji and /debuginfo Commands ───────────────────────────────────

# FIXED: Command handler to test Telegram Custom Premium Emoji rendering (REVISED: Invalid emoji tag removed) ✅
async def cmd_testemoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text_2_fallback = '<tg-emoji emoji-id="6037182932370590949">💀</tg-emoji> TEST 1 (Standard Custom Emoji Tag)'
    text_3 = '💀 TEST 2 (Plain Fallback Emoji)'
    
    tests = [
        ("Method 1: Nested <tg-emoji> Fallback", text_2_fallback, "HTML"),
        ("Method 2: Plain Fallback", text_3, None)
    ]
    await update.message.reply_text("🚀 <b>Starting Custom Emoji rendering tests...</b> Check server logs for response data.", parse_mode="HTML")
    for label, payload, parse_mode in tests:
        try:
            response = await context.bot.send_message(chat_id=chat_id, text=payload, parse_mode=parse_mode)
            await update.message.reply_text(f"✅ <b>{label} Succeeded</b>\nAPI Msg ID: <code>{response.message_id}</code>", parse_mode="HTML")
        except Exception as e: await update.message.reply_text(f"❌ <b>{label} Failed</b>\nError: <code>{html.escape(str(e))}</code>", parse_mode="HTML")


# FIXED: Command handler to show environment and library version diagnostics
async def cmd_debuginfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ptb_version = telegram.__version__
    python_version = sys.version
    
    info_text = (
        f"⚙️ <b>System Debug Information</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🐍 <b>Python Version:</b>\n<code>{html.escape(python_version)}</code>\n\n"
        f"🤖 <b>python-telegram-bot Version:</b>\n<code>{ptb_version}</code>\n\n"
        f"🌐 <b>Telegram Bot API Lib Info:</b>\n<code>ptb-asyncio-engine</code>\n\n"
        f"📝 <b>Active Command Parse Mode:</b>\n<code>HTML</code>"
    )
    await update.message.reply_text(info_text, parse_mode="HTML")


async def cmd_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_history_paginated(update.message.chat_id, context, offset=0)
async def cmd_members_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_members(update.message.chat_id, context)
async def cmd_payments_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id): await _send_payments(update.message.chat_id, context)


# FIXED: Reusable main menu reply buttons handler (DEFINED & IMPLEMENTED) ✅
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    uid = update.effective_user.id
    if not is_admin(uid): return

    if text == "📊 Dashboard":
        await update.message.reply_text(
            _build_dashboard_text(db.get_stats()),
            parse_mode="HTML",
            reply_markup=_dashboard_keyboard()
        )
    elif text == "📈 Analytics":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Submit History", callback_data="nav_history"), InlineKeyboardButton("⏳ Pending", callback_data="nav_pending")],
            [InlineKeyboardButton("📊 Detailed Stats", callback_data="nav_stats")]
        ])
        await update.message.reply_text("〔 📈 <b>Analytics & Reports</b> 〕\n" + DIVIDER + "\n\nSelect an option to view submission analytics:", parse_mode="HTML", reply_markup=kb)
    elif text == "💳 Payments":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Send Payment", callback_data="nav_sendpayment")],
            [InlineKeyboardButton("📋 Pay History", callback_data="nav_payments")],
            [InlineKeyboardButton("👥 Paid Members List", callback_data="nav_paidwho_0")]
        ])
        await update.message.reply_text("〔 💳 <b>Payment Management</b> 〕\n" + DIVIDER + "\n\nManage user payouts and transaction history:", parse_mode="HTML", reply_markup=kb)
    elif text == "⚙️ Settings":
        is_open = db.is_submissions_open()
        status_btn = InlineKeyboardButton("🔒 Close Submissions" if is_open else "🔓 Open Submissions", callback_data="nav_toggle_subs_settings")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠️ Manage Works", callback_data="nav_manage_tasks")],
            [InlineKeyboardButton("👥 Members", callback_data="nav_members")],
            [status_btn]
        ])
        await update.message.reply_text("〔 ⚙️ <b>Settings & Configuration</b> 〕\n" + DIVIDER + "\n\nAdjust your bot's operation parameters:", parse_mode="HTML", reply_markup=kb)


# ── App Factory ───────────────────────────────────────────────────────────────
def create_admin_app():
    app = Application.builder().token(ADMIN_BOT_TOKEN).build()

    pay_conv = ConversationHandler(
        entry_points=[
            CommandHandler("sendpayment", cmd_sendpayment),
            CallbackQueryHandler(cb_nav_sendpayment, pattern=r"^nav_sendpayment$"),  
            CallbackQueryHandler(cb_quickpay, pattern=r"^quickpay_"),               
        ],
        states={
            SELECT_USER: [CallbackQueryHandler(cb_select_user, pattern=r"^(payto_|pay_cancel)")],
            ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount),
                CallbackQueryHandler(cb_cancel_pay_callback, pattern=r"^pay_cancel$") 
            ],
            ENTER_NOTE: [
                CallbackQueryHandler(cb_note_skip, pattern=r"^note_skip$"),
                CallbackQueryHandler(cb_cancel_pay_callback, pattern=r"^pay_cancel$"), 
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_note)
            ],
            ATTACH_FILE: [
                CommandHandler("skip", cmd_skip_file),
                CallbackQueryHandler(cb_skip_file_callback, pattern=r"^file_skip$"),  
                CallbackQueryHandler(cb_cancel_pay_callback, pattern=r"^pay_cancel$"), 
                MessageHandler(filters.Document.ALL | filters.PHOTO, attach_file)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel_pay), CommandHandler("start", cmd_start)],
        per_message=False, allow_reentry=True
    )

    bc_conv = ConversationHandler(
        entry_points=[
            CommandHandler("broadcast", cmd_broadcast),
            CallbackQueryHandler(cb_nav_broadcast, pattern=r"^nav_broadcast$"), # FIXED: Registered dashboard button in ConversationHandler ✅
        ],
        states={
            BROADCAST_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, do_broadcast),
                CallbackQueryHandler(cb_cancel_broadcast, pattern=r"^bc_cancel$") 
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)],
        per_message=False, allow_reentry=True
    )

    # Task management conversation handler
    task_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_add_task_init, pattern=r"^add_task_init$")],
        states={
            ENTER_TASK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_task_name),
                CallbackQueryHandler(cb_cancel_task_callback, pattern=r"^task_cancel$") 
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel_task)],
        per_message=False, allow_reentry=True
    )

    app.add_handler(pay_conv)
    app.add_handler(bc_conv)
    app.add_handler(task_conv) 
    
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("testnotify", cmd_testnotify))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("history", cmd_history_cmd))
    app.add_handler(CommandHandler("members", cmd_members_cmd))
    app.add_handler(CommandHandler("payments", cmd_payments_cmd))
    
    # New debug testing commands registered here ✅
    app.add_handler(CommandHandler("testemoji", cmd_testemoji))
    app.add_handler(CommandHandler("debuginfo", cmd_debuginfo))
    
    # Callback query handlers
    app.add_handler(CallbackQueryHandler(cb_nav, pattern=r"^nav_"))
    app.add_handler(CallbackQueryHandler(cb_submission, pattern=r"^(approve|decline)_"))
    app.add_handler(CallbackQueryHandler(cb_member_detail, pattern=r"^member_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_delete_task, pattern=r"^deltask_\d+$")) 
    app.add_handler(CallbackQueryHandler(cb_paid_who, pattern=r"^nav_paidwho_")) # Paid members pagination handler
    app.add_handler(CallbackQueryHandler(cb_subhist_pagination, pattern=r"^nav_subhist_")) # Submission history pagination handler
    
    # Text buttons dispatcher registered at the end
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_text))
    return app
