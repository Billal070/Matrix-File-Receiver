import os
import telebot
from telebot import types
import sqlite3
import threading
from datetime import datetime

# ================= CONFIGURATION (Environment Variables) =================
# রেলওয়েতে সেট করা ভেরিয়েবল থেকে ডেটা নেওয়া হবে
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# ডেটাবেসের পাথ (রেলওয়ে ভলিউমের জন্য)
DB_PATH = os.getenv("DB_PATH", "bot_database.db")
# =========================================================================

# বট ইনিশিয়ালাইজেশন
user_bot = telebot.TeleBot(USER_BOT_TOKEN)
admin_bot = telebot.TeleBot(ADMIN_BOT_TOKEN)

user_states = {}
admin_states = {}

# ডেটাবেস কানেকশন হেল্পার
def run_query(query, params=(), fetch=False, commit=True):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchall() if fetch else None
    if commit:
        conn.commit()
    conn.close()
    return result

# ডেটাবেস টেবিল তৈরি
def init_db():
    run_query('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    joined_date TEXT)''')
    
    run_query('''CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    file_id TEXT,
                    file_name TEXT,
                    status TEXT,
                    timestamp TEXT)''')
    
    run_query('''CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    file_id TEXT,
                    status TEXT,
                    timestamp TEXT)''')

# ইউজার মেইন মেনু কিবোর্ড
def get_user_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_submit = types.KeyboardButton("📤 ফাইল জমা দিন")
    btn_profile = types.KeyboardButton("📊 আমার প্রোফাইল")
    btn_history = types.KeyboardButton("📜 হিস্ট্রি")
    markup.add(btn_submit)
    markup.add(btn_profile, btn_history)
    return markup

@user_bot.message_handler(commands=['start'])
def start_user(message):
    user_id = message.from_user.id
    username = message.from_user.username or "No Username"
    date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    user_exists = run_query("SELECT user_id FROM users WHERE user_id = ?", (user_id,), fetch=True)
    if not user_exists:
        run_query("INSERT INTO users (user_id, username, joined_date) VALUES (?, ?, ?)", (user_id, username, date_now))
        
    welcome_text = (
        f"👋 **আসসালামু আলাইকুম, {message.from_user.first_name}!**\n\n"
        "🤖 আমাদের ইউজার বটে আপনাকে স্বাগতম। এখান থেকে আপনি আপনার কাজের Excel (.xlsx) ফাইল জমা দিতে পারবেন এবং পেমেন্ট আপডেট পাবেন।"
    )
    user_bot.send_message(user_id, welcome_text, reply_markup=get_user_menu(), parse_mode="Markdown")

@user_bot.message_handler(func=lambda message: True)
def handle_user_menu(message):
    user_id = message.from_user.id
    
    if message.text == "📤 ফাইল জমা দিন":
        user_states[user_id] = "waiting_for_file"
        user_bot.send_message(user_id, "📁 দয়া করে আপনার **Google Sheet / Excel (.xlsx)** ফাইলটি এখানে ডকুমেন্ট হিসেবে আপলোড করুন।", parse_mode="Markdown")
        
    elif message.text == "📊 আমার প্রোফাইল":
        total_sub = run_query("SELECT COUNT(*) FROM submissions WHERE user_id = ?", (user_id,), fetch=True)[0][0]
        approved = run_query("SELECT COUNT(*) FROM submissions WHERE user_id = ? AND status = 'Approved'", (user_id,), fetch=True)[0][0]
        declined = run_query("SELECT COUNT(*) FROM submissions WHERE user_id = ? AND status = 'Declined'", (user_id,), fetch=True)[0][0]
        
        profile_text = (
            f"👤 **আপনার প্রোফাইল:**\n\n"
            f"🆔 **ইউজার আইডি:** `{user_id}`\n"
            f"📤 **মোট ফাইল জমা:** {total_sub} টি\n"
            f"🟢 **অ্যাপ্রুভড ফাইল:** {approved} টি\n"
            f"🔴 **রিজেক্টেড ফাইল:** {declined} টি"
        )
        user_bot.send_message(user_id, profile_text, parse_mode="Markdown")
        
    elif message.text == "📜 হিস্ট্রি":
        history = run_query("SELECT id, file_name, status, timestamp FROM submissions WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,), fetch=True)
        if not history:
            user_bot.send_message(user_id, "ℹ️ আপনার কোনো সাবমিশন হিস্ট্রি পাওয়া যায়নি।")
            return
            
        history_text = "📜 **আপনার শেষ ৫টি সাবমিশন হিস্ট্রি:**\n\n"
        for row in history:
            status_emoji = "⏳" if row[2] == "Pending" else ("🟢" if row[2] == "Approved" else "🔴")
            history_text += f"ID: #{row[0]} | 📄 {row[1]}\n📊 স্ট্যাটাস: {status_emoji} {row[2]}\n📅 সময়: {row[3]}\n------------------------\n"
        user_bot.send_message(user_id, history_text, parse_mode="Markdown")

@user_bot.message_handler(content_types=['document'])
def handle_user_file(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"User_{user_id}"
    
    if user_states.get(user_id) == "waiting_for_file":
        file_name = message.document.file_name
        
        if file_name.endswith(('.xlsx', '.xls')):
            file_id = message.document.file_id
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            run_query("INSERT INTO submissions (user_id, file_id, file_name, status, timestamp) VALUES (?, ?, ?, ?, ?)", 
                      (user_id, file_id, file_name, "Pending", date_now))
            
            sub_id = run_query("SELECT last_insert_rowid()", fetch=True)[0][0]
            
            user_bot.send_message(user_id, "✅ ফাইলটি সফলভাবে জমা হয়েছে। অ্যাডমিন চেক করার পর আপনাকে নোটিফাই করা হবে।", reply_markup=get_user_menu())
            user_states[user_id] = None
            
            admin_caption = (
                f"📥 **নতুন ফাইল জমা পড়েছে!**\n\n"
                f"👤 **ইউজার:** @{username} (ID: `{user_id}`)\n"
                f"📄 **ফাইলের নাম:** {file_name}\n"
                f"📅 **সময়:** {date_now}\n\n"
                f"ফাইলটি যাচাই করে নিচের বাটন চেপে সিদ্ধান্ত নিন:"
            )
            
            markup = types.InlineKeyboardMarkup()
            btn_approve = types.InlineKeyboardButton("🟢 Approve", callback_data=f"app_{sub_id}")
            btn_decline = types.InlineKeyboardButton("🔴 Decline", callback_data=f"dec_{sub_id}")
            markup.row(btn_approve, btn_decline)
            
            admin_bot.send_document(ADMIN_CHAT_ID, file_id, caption=admin_caption, reply_markup=markup, parse_mode="Markdown")
        else:
            user_bot.send_message(user_id, "⚠️ ভুল ফাইল ফরম্যাট! দয়া করে শুধুমাত্র Excel বা Google Sheet (.xlsx) ফাইল আপলোড করুন।")

# অ্যাডমিন মেইন কিবোর্ড
def get_admin_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_stats = types.KeyboardButton("📊 ওভারঅল স্ট্যাটিসটিক্স")
    btn_pay = types.KeyboardButton("💸 পেমেন্ট আপডেট পাঠান")
    markup.row(btn_stats, btn_pay)
    return markup

@admin_bot.message_handler(commands=['start'])
def start_admin(message):
    if message.from_user.id == ADMIN_CHAT_ID:
        admin_bot.send_message(ADMIN_CHAT_ID, "🛡️ **অ্যাডমিন প্যানেল বটে আপনাকে স্বাগতম!**\nএখানে ইউজারদের পাঠানো সকল কাজের ফাইল এবং পেমেন্ট কন্ট্রোল করতে পারবেন।", reply_markup=get_admin_menu(), parse_mode="Markdown")
    else:
        admin_bot.send_message(message.from_user.id, "❌ দুঃখিত, আপনি এই বটের অ্যাডমিন নন।")

@admin_bot.callback_query_handler(func=lambda call: True)
def handle_admin_callbacks(call):
    action, sub_id = call.data.split('_')
    sub_id = int(sub_id)
    
    sub_info = run_query("SELECT user_id, file_name FROM submissions WHERE id = ?", (sub_id,), fetch=True)
    if not sub_info:
        admin_bot.answer_callback_query(call.id, "❌ সাবমিশন ডেটা পাওয়া যায়নি!")
        return
        
    target_user_id, file_name = sub_info[0]
    
    if action == "app":
        run_query("UPDATE submissions SET status = 'Approved' WHERE id = ?", (sub_id,))
        
        user_msg = (
            f"🟢 **আপনার ফাইলটি অ্যাপ্রুভ হয়েছে!**\n\n"
            f"📄 **ফাইলের নাম:** {file_name}\n"
            f"ধন্যবাদ, আপনার কাজটি সফলভাবে রেকর্ড করা হয়েছে। 🤝"
        )
        try:
            user_bot.send_message(target_user_id, user_msg)
        except Exception as e:
            print(f"Error sending message to user: {e}")
            
        admin_bot.edit_message_caption(
            chat_id=ADMIN_CHAT_ID,
            message_id=call.message.message_id,
            caption=f"📄 **ফাইল:** {file_name}\n👤 **ইউজার আইডি:** `{target_user_id}`\n\n✅ **এই ফাইলটি Approved করা হয়েছে!**",
            reply_markup=None,
            parse_mode="Markdown"
        )
        admin_bot.answer_callback_query(call.id, "✅ ফাইলটি Approved করা হয়েছে।")
        
    elif action == "dec":
        run_query("UPDATE submissions SET status = 'Declined' WHERE id = ?", (sub_id,))
        
        user_msg = (
            f"🔴 **আপনার ফাইলটি রিজেক্ট (Decline) করা হয়েছে।**\n\n"
            f"📄 **ফাইলের নাম:** {file_name}\n"
            f"দয়া করে ফাইলটি সঠিক উপায়ে এডিট করে পুনরায় সাবমিট করুন।"
        )
        try:
            user_bot.send_message(target_user_id, user_msg)
        except Exception as e:
            print(f"Error sending message to user: {e}")
            
        admin_bot.edit_message_caption(
            chat_id=ADMIN_CHAT_ID,
            message_id=call.message.message_id,
            caption=f"📄 **ফাইল:** {file_name}\n👤 **ইউজার আইডি:** `{target_user_id}`\n\n❌ **এই ফাইলটি Declined করা হয়েছে!**",
            reply_markup=None,
            parse_mode="Markdown"
        )
        admin_bot.answer_callback_query(call.id, "❌ ফাইলটি Declined করা হয়েছে।")

@admin_bot.message_handler(func=lambda message: message.from_user.id == ADMIN_CHAT_ID)
def handle_admin_menu(message):
    if message.text == "📊 ওভারঅল স্ট্যাটিসটিক্স":
        total_users = run_query("SELECT COUNT(*) FROM users", fetch=True)[0][0]
        total_subs = run_query("SELECT COUNT(*) FROM submissions", fetch=True)[0][0]
        approved = run_query("SELECT COUNT(*) FROM submissions WHERE status = 'Approved'", fetch=True)[0][0]
        declined = run_query("SELECT COUNT(*) FROM submissions WHERE status = 'Declined'", fetch=True)[0][0]
        pending = run_query("SELECT COUNT(*) FROM submissions WHERE status = 'Pending'", fetch=True)[0][0]
        
        stats_text = (
            f"📊 **বটের সামগ্রিক স্ট্যাটিসটিক্স:**\n\n"
            f"👥 **মোট ইউজার সংখ্যা:** {total_users} জন\n"
            f"📂 **মোট জমা পড়া ফাইল:** {total_subs} টি\n"
            f"⏳ **পেন্ডিং ফাইল:** {pending} টি\n"
            f"🟢 **অ্যাপ্রুভড ফাইল:** {approved} টি\n"
            f"🔴 **রিজেক্টেড ফাইল:** {declined} টি"
        )
        admin_bot.send_message(ADMIN_CHAT_ID, stats_text, parse_mode="Markdown")
        
    elif message.text == "💸 পেমেন্ট আপডেট পাঠান":
        admin_states[ADMIN_CHAT_ID] = {"state": "waiting_for_user_id"}
        admin_bot.send_message(ADMIN_CHAT_ID, "👤 যে ইউজারকে পেমেন্ট আপডেট পাঠাতে চান, তার **User ID** (টেলিগ্রাম আইডি) দিন:\n*(ইউজারকে তার প্রোফাইল থেকে আইডিটি কপি করে দিতে বলুন)*", parse_mode="Markdown")

@admin_bot.message_handler(func=lambda message: message.from_user.id == ADMIN_CHAT_ID and ADMIN_CHAT_ID in admin_states)
def payment_flow_handler(message):
    state_data = admin_states[ADMIN_CHAT_ID]
    current_state = state_data.get("state")
    
    if current_state == "waiting_for_user_id":
        try:
            target_id = int(message.text)
            user_exists = run_query("SELECT user_id FROM users WHERE user_id = ?", (target_id,), fetch=True)
            if not user_exists:
                admin_bot.send_message(ADMIN_CHAT_ID, "⚠️ এই ইউজার আইডিটি বটের ডেটাবেসে পাওয়া যায়নি। সঠিক আইডি দিন:")
                return
                
            admin_states[ADMIN_CHAT_ID]["target_id"] = target_id
            admin_states[ADMIN_CHAT_ID]["state"] = "waiting_for_amount"
            admin_bot.send_message(ADMIN_CHAT_ID, "💰 এবার **টাকার পরিমাণ** (Amount in Taka) লিখে পাঠান:")
        except ValueError:
            admin_bot.send_message(ADMIN_CHAT_ID, "⚠️ অনুগ্রহ করে একটি সঠিক সংখ্যা (ইউজার আইডি) দিন।")
            
    elif current_state == "waiting_for_amount":
        try:
            amount = float(message.text)
            admin_states[ADMIN_CHAT_ID]["amount"] = amount
            admin_states[ADMIN_CHAT_ID]["state"] = "waiting_for_payment_file"
            admin_bot.send_message(ADMIN_CHAT_ID, "📄 হিসাবের জন্য কোনো ফাইল (Excel/PDF/Image) দিতে চাইলে ফাইলটি আপলোড করুন।\nফাইল ছাড়া শুধু নোটিফিকেশন পাঠাতে চাইলে `/skip` লিখে পাঠান।")
        except ValueError:
            admin_bot.send_message(ADMIN_CHAT_ID, "⚠️ অনুগ্রহ করে টাকার পরিমাণ সঠিক সংখ্যায় দিন।")

    elif current_state == "waiting_for_payment_file":
        target_id = state_data["target_id"]
        amount = state_data["amount"]
        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        file_id = None
        if message.content_types and 'document' in message.content_types:
            file_id = message.document.file_id
        
        run_query("INSERT INTO payments (user_id, amount, file_id, status, timestamp) VALUES (?, ?, ?, ?, ?)",
                  (target_id, amount, file_id, "Pending", date_now))
        
        user_notif_text = (
            f"💰 **নতুন পেমেন্ট হিসাব আপডেট!**\n\n"
            f"💵 **পেমেন্টের পরিমাণ:** {amount} টাকা\n"
            f"📅 **তারিখ:** {date_now}\n\n"
            f"📌 আপনার কাজের হিসাবের পেমেন্ট নোটিফিকেশন উপরে পাঠানো হলো। "
            f"আপনার পেমেন্টটি খুব দ্রুত ম্যানুয়ালি পরিশোধ করা হবে। কোনো প্রশ্ন থাকলে অ্যাডমিনের সাথে যোগাযোগ করুন। ধন্যবাদ! 🎉"
        )
        
        try:
            if file_id:
                user_bot.send_document(target_id, file_id, caption=user_notif_text)
            else:
                user_bot.send_message(target_id, user_notif_text)
            admin_bot.send_message(ADMIN_CHAT_ID, "✅ ইউজারকে পেমেন্ট আপডেট এবং ফাইল সফলভাবে পাঠানো হয়েছে!", reply_markup=get_admin_menu())
        except Exception as e:
            admin_bot.send_message(ADMIN_CHAT_ID, f"⚠️ ইউজার নোটিফিকেশন ব্যর্থ হয়েছে। কারণ: {e}", reply_markup=get_admin_menu())
            
        del admin_states[ADMIN_CHAT_ID]

@admin_bot.message_handler(commands=['skip'], func=lambda message: message.from_user.id == ADMIN_CHAT_ID)
def skip_payment_file(message):
    if ADMIN_CHAT_ID in admin_states and admin_states[ADMIN_CHAT_ID].get("state") == "waiting_for_payment_file":
        target_id = admin_states[ADMIN_CHAT_ID]["target_id"]
        amount = admin_states[ADMIN_CHAT_ID]["amount"]
        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        run_query("INSERT INTO payments (user_id, amount, file_id, status, timestamp) VALUES (?, ?, ?, ?, ?)",
                  (target_id, amount, None, "Pending", date_now))
        
        user_notif_text = (
            f"💰 **নতুন পেমেন্ট হিসাব আপডেট!**\n\n"
            f"💵 **পেমেন্টের পরিমাণ:** {amount} টাকা\n"
            f"📅 **তারিখ:** {date_now}\n\n"
            f"📌 আপনার কাজের পেমেন্ট প্রসেসিংয়ে রয়েছে। খুব শীঘ্রই ম্যানুয়ালি টাকা পাঠিয়ে দেওয়া হবে। ধন্যবাদ! 🎉"
        )
        
        try:
            user_bot.send_message(target_id, user_notif_text)
            admin_bot.send_message(ADMIN_CHAT_ID, "✅ ইউজারকে পেমেন্ট আপডেট নোটিফিকেশন সফলভাবে পাঠানো হয়েছে!", reply_markup=get_admin_menu())
        except Exception as e:
            admin_bot.send_message(ADMIN_CHAT_ID, f"⚠️ ইউজার নোটিফিকেশন ব্যর্থ হয়েছে। কারণ: {e}", reply_markup=get_admin_menu())
            
        del admin_states[ADMIN_CHAT_ID]

# মাল্টি-বট রানিং ইঞ্জিন
def run_user_bot():
    print("🤖 User Bot Online...")
    user_bot.infinity_polling()

def run_admin_bot():
    print("🛡️ Admin Bot Online...")
    admin_bot.infinity_polling()

if __name__ == '__main__':
    # কোড রান করার আগে ডিরেক্টরি চেক (রেলওয়ে ভলিউমের ফোল্ডার যাতে ঠিক থাকে)
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    init_db()  # ডেটাবেস সেটআপ
    
    t1 = threading.Thread(target=run_user_bot)
    t2 = threading.Thread(target=run_admin_bot)
    
    t1.start()
    t2.start()
