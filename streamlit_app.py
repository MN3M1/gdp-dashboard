import telebot
import threading
import time
import requests
import base64
from xml.etree import ElementTree as ET
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import json
from datetime import datetime
from telebot import types
import sqlite3
import math


ADMIN_ID = 706440281
BOT_TOKEN = "8136616031:AAH_fpXoytZqSR5tBLkXYp_dkjJd4VbTpko"


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class Database:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        with self.conn:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    username TEXT,
                    start_date TEXT
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY
                )
            """)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS banned_users (
                    id INTEGER PRIMARY KEY
                )
            """)
            # Add some default settings if they don't exist
            self.set_setting('bot_enabled', True)
            self.set_setting('subscription_enabled', False)
            # Correctly initialize subscription_channels with an empty list. The set_setting method will handle the JSON conversion.
            if self.get_setting('subscription_channels') is None:
                self.set_setting('subscription_channels', [])

            self.set_setting('join_notifications', True)
            self.set_setting('forward_messages', True)
            self.set_setting('start_message', "اهلا، بوت 100 ميجا اتصالات متجدده 😂🔥\n\nDevs:@W555W1/@M_N_3_M/@HY_49❤️‍🔥")
            
            self.add_admin(ADMIN_ID)

    def add_user(self, user_id, first_name, last_name, username):
        with self.conn:
            self.cursor.execute("INSERT OR IGNORE INTO users (id, first_name, last_name, username, start_date) VALUES (?, ?, ?, ?, ?)",
                                (user_id, first_name, last_name, username, datetime.now().isoformat()))

    def get_user_count(self):
        self.cursor.execute("SELECT COUNT(*) FROM users")
        return self.cursor.fetchone()[0]

    def get_users(self):
        self.cursor.execute("SELECT id FROM users")
        return [row[0] for row in self.cursor.fetchall()]

    def get_setting(self, key):
        self.cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
        result = self.cursor.fetchone()
        if result:
            value = result[0]
            if key == 'subscription_channels':
                try:
                    # Try to load as a list from JSON
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # If it's not a valid JSON list, assume it's a single channel string
                    # and return it as a list. This handles old database entries.
                    return [value] if value else []
            if value in ('True', 'False'):
                return value == 'True'
            return value
        return None

    def set_setting(self, key, value):
        with self.conn:
            if key == 'subscription_channels':
                value = json.dumps(value)
            elif isinstance(value, bool):
                value = str(value)
            self.cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

    def is_admin(self, user_id):
        self.cursor.execute("SELECT 1 FROM admins WHERE id=?", (user_id,))
        return self.cursor.fetchone() is not None

    def get_admins(self):
        self.cursor.execute("SELECT id FROM admins")
        return [row[0] for row in self.cursor.fetchall()]

    def add_admin(self, user_id):
        with self.conn:
            self.cursor.execute("INSERT OR IGNORE INTO admins (id) VALUES (?)", (user_id,))

    def remove_admin(self, user_id):
        with self.conn:
            self.cursor.execute("DELETE FROM admins WHERE id=?", (user_id,))

    def is_banned(self, user_id):
        self.cursor.execute("SELECT 1 FROM banned_users WHERE id=?", (user_id,))
        return self.cursor.fetchone() is not None

    def get_banned_users(self):
        self.cursor.execute("SELECT id FROM banned_users")
        return [row[0] for row in self.cursor.fetchall()]
        
    def ban_user(self, user_id):
        with self.conn:
            self.cursor.execute("INSERT OR IGNORE INTO banned_users (id) VALUES (?)", (user_id,))

    def unban_user(self, user_id):
        with self.conn:
            self.cursor.execute("DELETE FROM banned_users WHERE id=?", (user_id,))
            
    def clear_users(self):
        with self.conn:
            self.cursor.execute("DELETE FROM users")

    def clear_banned_users(self):
        with self.conn:
            self.cursor.execute("DELETE FROM banned_users")


class AdminDashboard:
    def __init__(self, db, bot):
        self.db = db
        self.bot = bot
        self.admin_states = {}
    
    def show_admin_menu(self, message):
        """Show main admin menu"""
        user_count = self.db.get_user_count()
        admin_count = len(self.db.get_admins())
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(types.InlineKeyboardButton("📈 Statistics", callback_data="admin_stats"))
        keyboard.row(
            types.InlineKeyboardButton("📮 Set Start Message", callback_data="admin_set_start"),
            types.InlineKeyboardButton("📊 Subscription Settings", callback_data="admin_subscription")
        )
        keyboard.row(
            types.InlineKeyboardButton("ℹ️ Notifications", callback_data="admin_notifications"),
            types.InlineKeyboardButton("👨‍💼 Admin Management", callback_data="admin_management")
        )
        keyboard.row(types.InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast"))
        keyboard.row(
            types.InlineKeyboardButton("🔧 Bot Settings", callback_data="admin_bot_settings"),
            types.InlineKeyboardButton("🚫 Ban Management", callback_data="admin_ban_management")
        )
        
        
        text = f"🤖 *- Admin Panel* 🔽\n⎯ ⎯ ⎯ ⎯ ⎯ ⎯ ⎯ ⎯\n"
        text += f"👥 Total Users: *{user_count}*\n"
        text += f"👨‍💼 Admins: *{admin_count}*\n"
        text += f"🤖 Bot Status: *{'✅ Active' if self.db.get_setting('bot_enabled') else '❌ Disabled'}*"
        
        
        self.bot.send_message(
            message.chat.id, text,
            parse_mode='Markdown', reply_markup=keyboard
        )

    def show_admin_menu_callback(self, call):
        """Show admin menu from callback"""
        user_count = self.db.get_user_count()
        admin_count = len(self.db.get_admins())

        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(types.InlineKeyboardButton("📈 Statistics", callback_data="admin_stats"))
        keyboard.row(
            types.InlineKeyboardButton("📮 Set Start Message", callback_data="admin_set_start"),
            types.InlineKeyboardButton("📊 Subscription Settings", callback_data="admin_subscription")
        )
        keyboard.row(
            types.InlineKeyboardButton("ℹ️ Notifications", callback_data="admin_notifications"),
            types.InlineKeyboardButton("👨‍💼 Admin Management", callback_data="admin_management")
        )
        keyboard.row(types.InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast"))
        keyboard.row(
            types.InlineKeyboardButton("🔧 Bot Settings", callback_data="admin_bot_settings"),
            types.InlineKeyboardButton("🚫 Ban Management", callback_data="admin_ban_management")
        )

        text = f"🤖 *- Admin Panel* 🔽\n⎯ ⎯ ⎯ ⎯ ⎯ ⎯ ⎯ ⎯\n"
        text += f"👥 Total Users: *{user_count}*\n"
        text += f"👨‍💼 Admins: *{admin_count}*\n"
        text += f"🤖 Bot Status: *{'✅ Active' if self.db.get_setting('bot_enabled') else '❌ Disabled'}*"

        self.bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    def handle_callback(self, call):
        """Handle admin callback queries"""
        data = call.data
        user_id = call.from_user.id
        
        
        if not (user_id == ADMIN_ID or self.db.is_admin(user_id)):
            self.bot.answer_callback_query(call.id, "❌ Access denied!")
            return
        
        
        self.bot.answer_callback_query(call.id)
        
        try:
            if data == "admin_back":
                return self.show_admin_menu_callback(call)
            
            elif data == "admin_stats":
                self.show_statistics(call)
            
            elif data == "admin_set_start":
                self.set_start_message_prompt(call)
            
            elif data == "admin_subscription":
                self.show_subscription_settings(call)
            
            elif data == "admin_notifications":
                self.show_notification_settings(call)
            
            elif data == "admin_management":
                self.show_admin_management(call)
            
            elif data == "admin_broadcast":
                self.broadcast_prompt(call)
            
            elif data == "admin_bot_settings":
                self.show_bot_settings(call)
            
            elif data == "admin_ban_management":
                self.show_ban_management(call)
            
            elif data.startswith("admin_toggle_"):
                self.handle_toggle(call, data)
            
            elif data.startswith("admin_ban_") or data.startswith("admin_unban_"):
                self.handle_ban_unban(call, data)

            elif data.startswith("admin_banned_list_"):
                self.show_banned_list(call, data)
            
            elif data.startswith("admin_user_list_"):
                self.show_user_list(call, data)

            elif data.startswith("admin_remove_channel_"):
                self.handle_remove_channel(call, data)
            
            elif data.startswith("admin_"):
                self.handle_specific_admin_action(call, data)
                
        except Exception as e:
            logging.error(f"Error in admin callback: {e}")
            self.bot.answer_callback_query(call.id, "❌ An error occurred!")
    
    def show_statistics(self, call):
        """Show bot statistics"""
        user_count = self.db.get_user_count()
        admin_count = len(self.db.get_admins())
        banned_count = len(self.db.get_banned_users())
        
        text = f"📈 *Bot Statistics*\n⎯ ⎯ ⎯ ⎯\n"
        text += f"👥 Total Users: {user_count}\n"
        text += f"👨‍💼 Admins: {admin_count}\n"
        text += f"🚫 Banned Users: {banned_count}\n"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(
            types.InlineKeyboardButton("👤 Show All Users", callback_data="admin_user_list_0"),
            types.InlineKeyboardButton("🚫 Show Banned Users", callback_data="admin_banned_list_0")
        )
        keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_stats"))
        
        self.bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode='Markdown', reply_markup=keyboard
        )

    def show_user_list(self, call, data):
        page = int(data.split('_')[-1])
        users = self.db.get_users()
        users_per_page = 10
        total_pages = math.ceil(len(users) / users_per_page)
        
        start_index = page * users_per_page
        end_index = start_index + users_per_page
        current_users = users[start_index:end_index]
        
        text = f"👤 *All Users* (Page {page + 1}/{total_pages})\n⎯ ⎯ ⎯ ⎯\n"
        if not current_users:
            text += "No users found."
        else:
            for user_id in current_users:
                text += f"ID: `{user_id}`\n"
        
        keyboard = types.InlineKeyboardMarkup()
        
        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_user_list_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton("➡️ Next", callback_data=f"admin_user_list_{page+1}"))
        
        keyboard.row(*nav_buttons)
        keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_stats"))
        
        self.bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode='Markdown', reply_markup=keyboard
        )

    def show_banned_list(self, call, data):
        page = int(data.split('_')[-1])
        banned_users = self.db.get_banned_users()
        users_per_page = 10
        total_pages = math.ceil(len(banned_users) / users_per_page)

        start_index = page * users_per_page
        end_index = start_index + users_per_page
        current_users = banned_users[start_index:end_index]

        text = f"🚫 *Banned Users* (Page {page + 1}/{total_pages})\n⎯ ⎯ ⎯ ⎯\n"
        if not current_users:
            text += "No banned users found."
        else:
            for user_id in current_users:
                text += f"ID: `{user_id}`\n"

        keyboard = types.InlineKeyboardMarkup()

        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_banned_list_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton("➡️ Next", callback_data=f"admin_banned_list_{page+1}"))

        keyboard.row(*nav_buttons)
        keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_stats"))

        self.bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    def show_subscription_settings(self, call):
        """Show subscription settings"""
        enabled = "✅" if self.db.get_setting('subscription_enabled') else "❎"
        channels = self.db.get_setting('subscription_channels')
        
        text = f"📊 *Subscription Settings* 🔽\n"
        text += f"Status: {enabled}\n⎯ ⎯ ⎯ ⎯\n"
        text += "📢 Channels:\n"
        if channels:
            for channel in channels:
                text += f"• `{channel}`\n"
        else:
            text += "No channels set.\n"

        
        keyboard = types.InlineKeyboardMarkup()
        for channel in channels:
            keyboard.row(types.InlineKeyboardButton(f"🗑️ Remove {channel}", callback_data=f"admin_remove_channel_{channel}"))
        
        keyboard.row(
            types.InlineKeyboardButton("➕ Add Channel", callback_data="admin_add_channel")
        )
        keyboard.row(types.InlineKeyboardButton(f"Subscription {enabled}", callback_data="admin_toggle_subscription"))
        keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_back"))
        
        self.bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    def handle_remove_channel(self, call, data):
        channel_to_remove = data.split('_', 3)[-1]
        channels = self.db.get_setting('subscription_channels')
        
        if channel_to_remove in channels:
            channels.remove(channel_to_remove)
            self.db.set_setting('subscription_channels', channels)
            self.bot.answer_callback_query(call.id, f"✅ Channel '{channel_to_remove}' removed!")
        else:
            self.bot.answer_callback_query(call.id, f"❌ Channel '{channel_to_remove}' not found!")
        
        self.show_subscription_settings(call)
    
    def show_notification_settings(self, call):
        """Show notification settings"""
        join_notif = "✅" if self.db.get_setting('join_notifications') else "❎"
        forward_msg = "✅" if self.db.get_setting('forward_messages') else "❎"
        
        text = "ℹ️ *Notification Settings* 🔽\n⎯ ⎯ ⎯ ⎯"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(types.InlineKeyboardButton(f"Join Notifications {join_notif}", callback_data="admin_toggle_join_notif"))
        keyboard.row(types.InlineKeyboardButton(f"Forward Messages {forward_msg}", callback_data="admin_toggle_forward"))
        keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_back"))
        
        self.bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    def show_admin_management(self, call):
        """Show admin management"""
        admins = self.db.get_admins()
        
        text = "👨‍💼 *Admin Management* 🔽\n⎯ ⎯ ⎯ ⎯\n"
        text += "You can add or remove admins using the buttons below ⚠️"
        
        keyboard = types.InlineKeyboardMarkup()
        for admin_id in admins:
            if admin_id == ADMIN_ID: continue
            try:
                admin_info = self.bot.get_chat(admin_id)
                name = admin_info.first_name or str(admin_id)
                keyboard.row(types.InlineKeyboardButton(f"🗑️ {name}", callback_data=f"admin_remove_admin_{admin_id}"))
            except:
                keyboard.row(types.InlineKeyboardButton(f"🗑️ {admin_id}", callback_data=f"admin_remove_admin_{admin_id}"))
        
        keyboard.row(types.InlineKeyboardButton("➕ Add Admin", callback_data="admin_add_admin"))
        keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_back"))
        
        self.bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    def show_bot_settings(self, call):
        """Show bot settings"""
        bot_enabled = "✅" if self.db.get_setting('bot_enabled') else "❎"
        
        text = "🔧 *Bot Settings* 🔽\n⎯ ⎯ ⎯ ⎯"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(types.InlineKeyboardButton(f"Bot Status {bot_enabled}", callback_data="admin_toggle_bot"))
        keyboard.row(types.InlineKeyboardButton("🗑️ Clear Users", callback_data="admin_clear_users"))
        keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_back"))
        
        self.bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    def show_ban_management(self, call):
        """Show ban management"""
        banned_users = self.db.get_banned_users()
        banned_count = len(banned_users)
        
        text = f"🚫 *Ban Management* 🔽\n⎯ ⎯ ⎯ ⎯\n"
        text += f"Banned Users: {banned_count}"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(
            types.InlineKeyboardButton("➕ Ban User", callback_data="admin_ban_user"),
            types.InlineKeyboardButton("➖ Unban User", callback_data="admin_unban_user")
        )
        keyboard.row(types.InlineKeyboardButton("🗑️ Clear All Bans", callback_data="admin_clear_bans"))
        keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_back"))
        
        self.bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode='Markdown', reply_markup=keyboard
        )
    
    def handle_toggle(self, call, data):
        """Handle toggle actions"""
        if data == "admin_toggle_subscription":
            current = self.db.get_setting('subscription_enabled')
            self.db.set_setting('subscription_enabled', not current)
            self.show_subscription_settings(call)
        
        elif data == "admin_toggle_join_notif":
            current = self.db.get_setting('join_notifications')
            self.db.set_setting('join_notifications', not current)
            self.show_notification_settings(call)
        
        elif data == "admin_toggle_forward":
            current = self.db.get_setting('forward_messages')
            self.db.set_setting('forward_messages', not current)
            self.show_notification_settings(call)
        
        elif data == "admin_toggle_bot":
            current = self.db.get_setting('bot_enabled')
            self.db.set_setting('bot_enabled', not current)
            self.show_bot_settings(call)
    
    def handle_ban_unban(self, call, data):
        if data == "admin_ban_user":
            self.admin_states[call.from_user.id] = "waiting_ban_id"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_ban_management"))
            self.bot.edit_message_text(
                "➕ Send the user ID to ban 🚫",
                call.message.chat.id, call.message.message_id,
                reply_markup=keyboard
            )
        elif data == "admin_unban_user":
            self.admin_states[call.from_user.id] = "waiting_unban_id"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_ban_management"))
            self.bot.edit_message_text(
                "➖ Send the user ID to unban ✅",
                call.message.chat.id, call.message.message_id,
                reply_markup=keyboard
            )
        elif data.startswith("admin_ban_user_") or data.startswith("admin_unban_user_"):
            parts = data.split('_')
            action = parts[1]
            user_id_to_manage = int(parts[-1])
            if action == 'ban':
                self.db.ban_user(user_id_to_manage)
                self.bot.answer_callback_query(call.id, "✅ User banned!")
            elif action == 'unban':
                self.db.unban_user(user_id_to_manage)
                self.bot.answer_callback_query(call.id, "✅ User unbanned!")
            self.show_ban_management(call)
    
    def handle_specific_admin_action(self, call, data):
        """Handle specific admin actions"""
        if data == "admin_add_channel":
            self.admin_states[call.from_user.id] = "waiting_channel"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_subscription"))
            
            self.bot.edit_message_text(
                "📢 Send the channel username without @ (e.g., mychannel) ⏳",
                call.message.chat.id, call.message.message_id,
                reply_markup=keyboard
            )
        
        elif data == "admin_add_admin":
            self.admin_states[call.from_user.id] = "waiting_admin_id"
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_management"))
            
            self.bot.edit_message_text(
                "👨‍💼 Send the user ID of the new admin ℹ️",
                call.message.chat.id, call.message.message_id,
                reply_markup=keyboard
            )
        
        elif data.startswith("admin_remove_admin_"):
            admin_id = int(data.split("_")[-1])
            if admin_id == ADMIN_ID:
                self.bot.answer_callback_query(call.id, "❌ Cannot remove main admin!")
                return
            self.db.remove_admin(admin_id)
            self.bot.answer_callback_query(call.id, "✅ Admin removed!")
            self.show_admin_management(call)
        
        elif data == "admin_clear_users":
            self.db.clear_users()
            self.bot.answer_callback_query(call.id, "✅ All users cleared!")
            self.show_bot_settings(call)
        
        elif data == "admin_clear_bans":
            self.db.clear_banned_users()
            self.bot.answer_callback_query(call.id, "✅ All bans cleared!")
            self.show_ban_management(call)
    
    def set_start_message_prompt(self, call):
        """Prompt for start message"""
        self.admin_states[call.from_user.id] = "waiting_start_message"
        current_message = self.db.get_setting('start_message') or "Default welcome message"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_back"))
        
        self.bot.edit_message_text(
            f"📮 Send the new start message ⏳\n\nCurrent message: {current_message}",
            call.message.chat.id, call.message.message_id,
            reply_markup=keyboard
        )
    
    def broadcast_prompt(self, call):
        """Prompt for broadcast message"""
        user_count = self.db.get_user_count()
        self.admin_states[call.from_user.id] = "waiting_broadcast"
        
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_back"))
        
        self.bot.edit_message_text(
            f"📨 Send the message to broadcast ⏳\n\nUsers: {user_count}",
            call.message.chat.id, call.message.message_id,
            reply_markup=keyboard
        )
    
    def handle_message(self, message):
        """Handle admin messages based on state"""
        user_id = message.from_user.id
        state = self.admin_states.get(user_id)
        
        if not state:
            return False
        
        if state == "waiting_channel":
            channel = message.text.strip()
            channels = self.db.get_setting('subscription_channels')
            if not isinstance(channels, list):  # This line is added to fix the error
                channels = []
            if channel not in channels:
                channels.append(channel)
                self.db.set_setting('subscription_channels', channels)
                reply_text = f"✅ Channel '{channel}' added successfully!"
            else:
                reply_text = f"❌ Channel '{channel}' is already in the list."

            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_subscription"))
            
            self.bot.reply_to(
                message, reply_text,
                reply_markup=keyboard
            )
            
            del self.admin_states[user_id]
            return True
        
        elif state == "waiting_admin_id":
            try:
                admin_id = int(message.text.strip())
                self.db.add_admin(admin_id)
                keyboard = types.InlineKeyboardMarkup()
                keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_management"))
                
                self.bot.reply_to(
                    message, f"✅ Admin {admin_id} added successfully!",
                    reply_markup=keyboard
                )
                
                try:
                    self.bot.send_message(
                        admin_id,
                        "✅ You have been promoted to admin!\nUse /admin to access admin panel."
                    )
                except:
                    pass
                
            except ValueError:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_management"))
                
                self.bot.reply_to(
                    message, "❌ Please send a valid user ID (numbers only)",
                    reply_markup=keyboard
                )
            del self.admin_states[user_id]
            return True

        elif state == "waiting_ban_id":
            try:
                user_id_to_ban = int(message.text.strip())
                self.db.ban_user(user_id_to_ban)
                keyboard = types.InlineKeyboardMarkup()
                keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_ban_management"))
                self.bot.reply_to(message, f"✅ User {user_id_to_ban} banned successfully!", reply_markup=keyboard)
            except ValueError:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_ban_management"))
                self.bot.reply_to(message, "❌ Please send a valid user ID (numbers only)", reply_markup=keyboard)
            del self.admin_states[user_id]
            return True
            
        elif state == "waiting_unban_id":
            try:
                user_id_to_unban = int(message.text.strip())
                self.db.unban_user(user_id_to_unban)
                keyboard = types.InlineKeyboardMarkup()
                keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_ban_management"))
                self.bot.reply_to(message, f"✅ User {user_id_to_unban} unbanned successfully!", reply_markup=keyboard)
            except ValueError:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_ban_management"))
                self.bot.reply_to(message, "❌ Please send a valid user ID (numbers only)", reply_markup=keyboard)
            del self.admin_states[user_id]
            return True
        
        elif state == "waiting_start_message":
            message_text = message.text
            self.db.set_setting('start_message', message_text)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_back"))
            
            self.bot.reply_to(
                message, f"✅ Start message updated to:\n{message_text}",
                reply_markup=keyboard
            )
            del self.admin_states[user_id]
            return True
        
        elif state == "waiting_broadcast":
            message_text = message.text
            users = self.db.get_users()
            
            
            sent_count = 0
            failed_count = 0
            
            progress_msg = self.bot.reply_to(message, "📨 Broadcasting message...")
            
            for user in users:
                try:
                    self.bot.send_message(user, message_text, parse_mode='Markdown')
                    sent_count += 1
                except Exception as e:
                    failed_count += 1
                
                
                if (sent_count + failed_count) % 10 == 0:
                    try:
                        self.bot.edit_message_text(
                            f"📨 Broadcasting... {sent_count + failed_count}/{len(users)}",
                            progress_msg.chat.id, progress_msg.message_id
                        )
                    except:
                        pass
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(types.InlineKeyboardButton("↪️ Back", callback_data="admin_back"))
            
            self.bot.edit_message_text(
                f"✅ Broadcast completed!\n"
                f"📤 Sent: {sent_count}\n"
                f"❌ Failed: {failed_count}",
                progress_msg.chat.id, progress_msg.message_id,
                reply_markup=keyboard
            )
            del self.admin_states[user_id]
            return True
        
        return False
        

bot = telebot.TeleBot(BOT_TOKEN)


db = Database('bot0.db')
admin_dashboard = AdminDashboard(db, bot)


user_sessions = {}


stop_keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
stop_keyboard.add(telebot.types.KeyboardButton("STOP🛑"))

def print_colored(text, color):
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'purple': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'reset': '\033[0m'
    }
    print(f"{colors.get(color, colors['white'])}{text}{colors['reset']}")

def create_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

def login(email, password, chat_id):
    url = "https://mab.etisalat.com.eg:11003/Saytar/rest/authentication/loginWithPlan"
    headers = {
        'ADRUM': 'isAjax:true',
        'ADRUM_1': 'isMobile:true',
        'APP-BuildNumber': '10625',
        'APP-STORE': 'GOOGLE',
        'APP-Version': '32.0.0',
        'Accept': 'text/xml',
        'Accept-Encoding': 'gzip',
        'Authorization': f'Basic {base64.b64encode(f"{email}:{password}".encode()).decode()}',
        'Connection': 'Keep-Alive',
        'Content-Type': 'text/xml; charset=UTF-8',
        'Host': 'mab.etisalat.com.eg:11003',
        'Is-Corporate': 'false',
        'Language': 'ar',
        'OS-Type': 'Android',
        'OS-Version': '12',
        'User-Agent': 'okhttp/5.0.0-alpha.11',
        'applicationName': 'MAB',
        'applicationVersion': '2',
        'bodySignature': '818ecb2021fd0954ea77d37a0d2515089badc58bd82f0763b95c7f29c410a2e5272a0f4798172857c990770991bbb091105e14c686d9600c4cd0c78f0956fe74',
        'headerSignature': '8198cf423fd9283b69650c3b803ec4d71e1504423e98b95686400fdd8835dc7413fe896f819173f84458cc1641493b069e1bb75c7eb188e980ececc7af4261b1',
        'urlSignature': 'b5269b0647ce686909fc474b3fd5fbac566b061abe28590c1a0b6cc1ea633fb3d2af498ede2680f81ebe0f78eb9c46b6cb6aa5bf80c4b12b8cdaa4c01f4659a1'
    }
    payload = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
    <loginRequest>
        <deviceId>60bd1f40a76e1cf7</deviceId>
        <firstLoginAttempt>true</firstLoginAttempt>
        <modelType>RMX3760</modelType>
        <osVersion>12</osVersion>
        <platform>Android</platform>
        <udid>60bd1f40a76e1cf7</udid>
    </loginRequest>"""
    try:
        session = create_session()
        response = session.post(url, data=payload, headers=headers, timeout=10)
        logging.info(f"Login attempt for user {chat_id}: Status Code {response.status_code}")
        return response
    except requests.exceptions.RequestException as e:
        logging.error(f"Login failed for user {chat_id} due to connection issue: {e}")
        bot.send_message(chat_id, f"❌ERROR:  {str(e)}")
        return None

def submit_order(msisdn, auth_token, cookies, operation, product_name, chat_id):
    url = "https://mab.etisalat.com.eg:11003/Saytar/rest/servicemanagement/submitOrderV2"
    payload = f"""<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
    <submitOrderRequest>
        <mabOperation></mabOperation>
        <msisdn>{msisdn}</msisdn>
        <operation>{operation}</operation>
        <productName>{product_name}</productName>
    </submitOrderRequest>"""
    headers = {
        'Host': "mab.etisalat.com.eg:11003",
        'User-Agent': "okhttp/5.0.0-alpha.11",
        'Connection': "Keep-Alive",
        'Accept': "text/xml",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/xml",
        'applicationVersion': "2",
        'applicationName': "MAB",
        'Language': "ar",
        'APP-BuildNumber': "10651",
        'APP-Version': "33.2.0",
        'OS-Type': "Android",
        'OS-Version': "10",
        'APP-STORE': "GOOGLE",
        'C-Type': "4G",
        'auth': f"Bearer {auth_token}",
        'Is-Corporate': "false",
        'headerSignature': "4b3dcb4f7c1f5e12db8113b77ef0138760841c20a39d903bc102e63a4975fa47f28a4b25847458e9d48ea12d1288365a4e97ec2009275338631c448e392c3ad7",
        'urlSignature': "0580a5d9943fbe0df200ac6d64dc8cf9197e8d4afcffaa22afcbcb88c6336eeb8144cbb39223b18bc49e49ca902f20da687486ce47ceb0d4b3cc8646ea7cc935",
        'bodySignature': "9fed60daa7dc4ce5bcc9b340b06f276069a06e7fc5a0ad24c9d39d3e7a69b96201d631f68d1ac30205f0eda8e6b673e25efb171f92fd1c8eb61aac8d32106a9",
        'Content-Type': "text/xml; charset=UTF-8",
        'Cookie': cookies
    }
    try:
        session = create_session()
        response = session.post(url, data=payload, headers=headers, timeout=10)
        logging.info(f"Submit order for {product_name} by user {chat_id}: Status Code {response.status_code}")
        return response
    except requests.exceptions.RequestException as e:
        logging.error(f"Submit order for {product_name} by user {chat_id} failed: {e}")
        bot.send_message(chat_id, f"❌ERROR: {str(e)}")
        return None

def check_consumption(msisdn, auth_token, cookies, chat_id):
    url = f"https://mab.etisalat.com.eg:11003/Saytar/rest/servicemanagement/getGenericConsumptionsV2?requestParam=%3CdialAndLanguageRequest%3E%3CsegmentId%3EPIXEL%3C%2FsegmentId%3E%3CsubscriberNumber%3E{msisdn}%3C%2FsubscriberNumber%3E%3Clanguage%3E1%3C%2Flanguage%3E%3CshortCode%3EPIXB%3C%2FshortCode%3E%3C%2FdialAndLanguageRequest%3E"
    headers = {
        'Host': "mab.etisalat.com.eg:11003",
        'User-Agent': "okhttp/5.0.0-alpha.11",
        'Connection': "Keep-Alive",
        'Accept': "text/xml",
        'Accept-Encoding': "gzip",
        'applicationVersion': "2",
        'Content-Type': "text/xml",
        'applicationName': "MAB",
        'Language': "ar",
        'APP-BuildNumber': "10651",
        'APP-Version': "33.2.0",
        'OS-Type': "Android",
        'OS-Version': "10",
        'APP-STORE': "GOOGLE",
        'C-Type': "4G",
        'auth': f"Bearer {auth_token}",
        'Is-Corporate': "false",
        'headerSignature': "fc16ca3ea778ed01db4c85927fe5c055bf48ba492b718569703b2b96b306a13c5b4f4da2dd9a9b61c484dbd4575637bc916dea4a634c109fc46253c858ac636e",
        'urlSignature': "8d7935d9943fbe0df200ac6d64dc8cf9197e8d4afcffaa22afcbcb88c6336eeb8144cbb39223b18bc49e49ca902f20da687486ce47ceb0d4b3cc8646ea7cc935",
        'ADRUM_1': "isMobile:true",
        'ADRUM': "isAjax:true",
        'Cookie': cookies
    }
    try:
        session = create_session()
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for consumption in root.findall(".//consumption"):
                product_id = consumption.find("productId")
                if product_id is not None and product_id.text == "GIFTS_FAN_ZONE":
                    consumed_value = float(consumption.find("consumedValue").text)
                    remaining_value = float(consumption.find("remainingValue").text)
                    total_value = float(consumption.find("totalValue").text)
                    logging.info(f"User {chat_id} consumption check: {consumed_value:.2f}/{total_value:.2f} MB")
                    return consumed_value, remaining_value, total_value
        return None, None, None
    except Exception as e:
        logging.error(f"Consumption check failed for user {chat_id}: {e}")
        return None, None, None

def execute_all_scripts(msisdn, auth_token, cookies, chat_id):
    bot.send_message(chat_id, "WAIT 👀🚀")
    logging.info(f"Executing scripts for user {chat_id}")
    
    
    response_activate1 = submit_order(msisdn, auth_token, cookies, "ACTIVATE", "ALBUMS_FAN_ZONE", chat_id)
    if response_activate1 and response_activate1.status_code == 200:
        bot.send_message(chat_id, "DONE (1/3)✅")
    else:
        bot.send_message(chat_id, "❌ERROR")
    
    time.sleep(6)
    
    
    response_unsubscribe = submit_order(msisdn, auth_token, cookies, "UNSUBSCRIBE_FANZONE", "MAIN_FAN_ZONE", chat_id)
    if response_unsubscribe and response_unsubscribe.status_code == 200:
        bot.send_message(chat_id, "DONE (2/3)✅")
    else:
        bot.send_message(chat_id, "❌ERROR")
    
    time.sleep(6)
    
    
    response_activate2 = submit_order(msisdn, auth_token, cookies, "ACTIVATE", "ALBUMS_FAN_ZONE", chat_id)
    if response_activate2 and response_activate2.status_code == 200:
        bot.send_message(chat_id, "DONE (3/3)✅")
    else:
        bot.send_message(chat_id, "ERROR❌")
    
    bot.send_message(chat_id, "🔄 Package renewed ")
    logging.info(f"Scripts executed successfully for user {chat_id}")

def run_script(chat_id):
    session = user_sessions[chat_id]
    msisdn = session['msisdn']
    email = session['email']
    password = session['password']
    
    
    if False:
        bot.send_message(chat_id, "WAIT.")

    logging.info(f"Starting script for user {chat_id}")
    
    
    login_response = login(email, password, chat_id)
    if login_response is None or login_response.status_code != 200:
        bot.send_message(chat_id, "ERROR❌")
        user_sessions[chat_id]['running'] = False
        return
    
    auth_token = login_response.headers.get('auth', '')
    cookies = login_response.headers.get('Set-Cookie', '')
    
    if not auth_token:
        bot.send_message(chat_id, "ERROR❌")
        user_sessions[chat_id]['running'] = False
        return
    
    bot.send_message(chat_id, "Done Login✅")
    execute_all_scripts(msisdn, auth_token, cookies, chat_id)
    
    retry_count = 0
    max_retries = 5 
    
    while user_sessions.get(chat_id, {}).get('running', False):
        try:
            time.sleep(20)
            consumed, remaining, total = check_consumption(msisdn, auth_token, cookies, chat_id)
            
            if consumed is not None and total is not None:
                percentage_consumed = (consumed / total) * 100
                logging.info(f"User {chat_id}: Consumption is {percentage_consumed:.2f}%")
                
                
                if percentage_consumed >= 70:
                    bot.send_message(chat_id, "⚠️ Package expired")
                    execute_all_scripts(msisdn, auth_token, cookies, chat_id)
            else:
                logging.warning(f"User {chat_id}: Failed to check consumption, retrying...")
                
                retry_count += 1
                if retry_count >= max_retries:
                    bot.send_message(chat_id, "❌ERROR")
                    user_sessions[chat_id]['running'] = False
                    break
                
                
                login_response = login(email, password, chat_id)
                if login_response is None or login_response.status_code != 200:
                    bot.send_message(chat_id, "ERROR❌")
                    user_sessions[chat_id]['running'] = False
                    break
                
                auth_token = login_response.headers.get('auth', '')
                cookies = login_response.headers.get('Set-Cookie', '')
                
                if not auth_token:
                    bot.send_message(chat_id, "❌ERROR")
                    user_sessions[chat_id]['running'] = False
                    break

            
            time.sleep(10)

        except Exception as e:
            logging.error(f"An unexpected error occurred for user {chat_id}: {e}")
            bot.send_message(chat_id, f"❌ERROR: ")
            
            break
            
    logging.info(f"Script for user {chat_id} has stopped.")

def check_subscription(user_id):
    if not db.get_setting('subscription_enabled'):
        return True, None
    
    channels = db.get_setting('subscription_channels')
    if not channels:
        return True, None
        
    for channel in channels:
        try:
            member = bot.get_chat_member(f'@{channel}', user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False, channel
        except telebot.apihelper.ApiException as e:
            if 'chat not found' in str(e).lower():
                logging.error(f"Channel @{channel} not found. Admin needs to check the channel name.")
            else:
                logging.error(f"Error checking subscription for user {user_id} in channel @{channel}: {e}")
            return False, channel
    return True, None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_info = message.from_user
    
    if not db.get_setting('bot_enabled') and not db.is_admin(chat_id):
        bot.send_message(chat_id, "❌ The bot is currently disabled by the admin.")
        return
        
    if db.is_banned(chat_id):
        logging.info(f"Banned user {chat_id} tried to start the bot. Ignoring.")
        return
    
    is_new_user = not db.cursor.execute("SELECT 1 FROM users WHERE id=?", (chat_id,)).fetchone()
    db.add_user(chat_id, user_info.first_name, user_info.last_name, user_info.username)

    if db.get_setting('join_notifications') and is_new_user:
        user_info_text = (
            f"🆕 New user joined!\n"
            f"👤 User ID: `{chat_id}`\n"
            f"📛 Name: {user_info.first_name or ''} {user_info.last_name or ''}\n"
            f"🔗 Username: @{user_info.username or 'N/A'}"
        )
        for admin_id in db.get_admins():
            try:
                bot.send_message(admin_id, user_info_text, parse_mode='Markdown')
            except Exception as e:
                logging.error(f"Failed to send join notification to admin {admin_id}: {e}")
    
    is_subscribed, missing_channel = check_subscription(chat_id)
    if not is_subscribed:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Join Channel", url=f"https://t.me/{missing_channel}"))
        bot.send_message(
            chat_id,
            f"⚠️ Please join our channel to use the bot: https://t.me/{missing_channel}",
            reply_markup=keyboard
        )
        return

    if chat_id in user_sessions and user_sessions[chat_id].get('running', False):
        bot.send_message(chat_id, "THE BOT IS RUNNIG IF YOU WANT TO STOP IT PRESS STOP")
        return
    
    user_sessions[chat_id] = {'running': False}
    logging.info(f"User {chat_id} started the bot.")
    
    start_message = db.get_setting('start_message')
    
    bot.send_message(chat_id, start_message)
    bot.send_message(chat_id, "📞 SEND MOBILE NUMBER:")

@bot.message_handler(commands=['admin'])
def show_admin_panel(message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID or db.is_admin(user_id):
        admin_dashboard.show_admin_menu(message)
    else:
        bot.send_message(user_id, "□□□□□□□□□□□□□□□□□□□□□□")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_callback(call):
    admin_dashboard.handle_callback(call)

@bot.message_handler(func=lambda message: admin_dashboard.handle_message(message))
def handle_admin_state_message(message):
    pass

@bot.message_handler(func=lambda message: message.text == "STOP🛑")
def stop_script(message):
    chat_id = message.chat.id
    
    if not db.get_setting('bot_enabled') and not db.is_admin(chat_id):
        return
        
    if db.is_banned(chat_id):
        return
        
    if chat_id in user_sessions and user_sessions[chat_id].get('running', False):
        user_sessions[chat_id]['running'] = False
        bot.send_message(chat_id, "⏹BOT STOPPED", reply_markup=telebot.types.ReplyKeyboardRemove())
        logging.info(f"User {chat_id} stopped the script.")
    else:
        bot.send_message(chat_id, "❌ENTER YOUR ACCOUNT INFO FIRST!\n\n/start")

@bot.message_handler(func=lambda message: message.text and not user_sessions.get(message.chat.id, {}).get('msisdn'))
def get_number(message):
    chat_id = message.chat.id
    
    if not db.get_setting('bot_enabled') and not db.is_admin(chat_id):
        return
        
    if db.is_banned(chat_id):
        return
    
    is_subscribed, missing_channel = check_subscription(chat_id)
    if not is_subscribed:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Join Channel", url=f"https://t.me/{missing_channel}"))
        bot.send_message(
            chat_id,
            f"⚠️ Please join our channel to use the bot: https://t.me/{missing_channel}",
            reply_markup=keyboard
        )
        return

    phone_number = message.text.strip()
    
    
    if phone_number.startswith('0') and len(phone_number) == 11 and phone_number.isdigit():
        processed_number = phone_number[1:]
    elif len(phone_number) == 10 and phone_number.isdigit():
        processed_number = phone_number
    else:
        bot.send_message(chat_id, "❌INVAILD NUMBER! Please send a valid 10 or 11-digit number.")
        return
    
    user_sessions[chat_id]['msisdn'] = processed_number
    logging.info(f"User {chat_id} provided phone number: {processed_number}.")
    bot.send_message(chat_id, "📧ENTER EMAIL:")

@bot.message_handler(func=lambda message: message.text and user_sessions.get(message.chat.id, {}).get('msisdn') and not user_sessions.get(message.chat.id, {}).get('email'))
def get_email(message):
    chat_id = message.chat.id
    
    if not db.get_setting('bot_enabled') and not db.is_admin(chat_id):
        return
        
    if db.is_banned(chat_id):
        return

    is_subscribed, missing_channel = check_subscription(chat_id)
    if not is_subscribed:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Join Channel", url=f"https://t.me/{missing_channel}"))
        bot.send_message(
            chat_id,
            f"⚠️ Please join our channel to use the bot: https://t.me/{missing_channel}",
            reply_markup=keyboard
        )
        return
        
    if '@' not in message.text or '.' not in message.text:
        bot.send_message(chat_id, "❌INVAILD EMAIL!")
        return
    
    user_sessions[chat_id]['email'] = message.text
    logging.info(f"User {chat_id} provided email.")
    bot.send_message(chat_id, "🔑ENTER PASSWORD:")

@bot.message_handler(func=lambda message: message.text and user_sessions.get(message.chat.id, {}).get('email') and not user_sessions.get(message.chat.id, {}).get('password'))
def get_password(message):
    chat_id = message.chat.id
    
    if not db.get_setting('bot_enabled') and not db.is_admin(chat_id):
        return
        
    if db.is_banned(chat_id):
        return

    is_subscribed, missing_channel = check_subscription(chat_id)
    if not is_subscribed:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Join Channel", url=f"https://t.me/{missing_channel}"))
        bot.send_message(
            chat_id,
            f"⚠️ Please join our channel to use the bot: https://t.me/{missing_channel}",
            reply_markup=keyboard
        )
        return
    
    if len(message.text) < 4:
        bot.send_message(chat_id, "❌ THE PASSWORD IS TOO SHORT !")
        return
    
    user_sessions[chat_id]['password'] = message.text
    logging.info(f"User {chat_id} provided password. Starting script...")
    bot.send_message(chat_id, "🔄WAIT...........", reply_markup=stop_keyboard)
    
    
    user_sessions[chat_id]['running'] = True
    thread = threading.Thread(target=run_script, args=(chat_id,))
    thread.start()


@bot.message_handler(func=lambda message: True)
def default_handler(message):
    
    if not db.get_setting('bot_enabled') and not db.is_admin(message.chat.id):
        return
        
    if db.is_banned(message.chat.id):
        return
    
    is_subscribed, missing_channel = check_subscription(message.chat.id)
    if not is_subscribed:
        return
        
    if not admin_dashboard.handle_message(message):
        bot.send_message(message.chat.id, "ERROR ❌")


print("V I R U S")
bot.infinity_polling()
