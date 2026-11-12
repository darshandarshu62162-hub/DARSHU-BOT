import os
import time
import sqlite3
import asyncio
import logging
import signal
from pathlib import Path
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ==========================================
# DARSHU BHAI HOSTING BOT
# ==========================================

BOT_TOKEN = "9263656949:AAHSNpL-rm1sMuPPvOK9-lXVUcksMwTSOMk"
OWNER_ID = 8370094461
CONTACT_OWNER = "@Darshu95"

DB = "hosting.db"
BASE_DIR = Path("hosting_files").resolve()
BASE_DIR.mkdir(exist_ok=True)

# Set your updates channel, e.g. @YourChannel
UPDATES_CHANNEL = os.getenv("https://t.me/+-zxO2Yc9VFRiMDE1"

# IMPORTANT: Only owner can execute uploaded scripts.
OWNER_ONLY_RUN = True

MAX_FILE_SIZE = 5 * 1024 * 1024
processes = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger("DARSHU_BHAI")


# ==========================================
# DATABASE
# ==========================================

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS users(
            uid INTEGER PRIMARY KEY,
            username TEXT,
            joined TEXT,
            premium_until TEXT DEFAULT '',
            banned INTEGER DEFAULT 0
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS files(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            filename TEXT,
            path TEXT,
            created TEXT
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS admins(
            uid INTEGER PRIMARY KEY
        )
        """)

        defaults = {
            "locked": "0",
            "channel": UPDATES_CHANNEL,
        }

        for key, value in defaults.items():
            con.execute(
                "INSERT OR IGNORE INTO settings VALUES (?,?)",
                (key, value)
            )


def setting(key):
    with db() as con:
        row = con.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else ""


def set_setting(key, value):
    with db() as con:
        con.execute(
            "INSERT OR REPLACE INTO settings VALUES (?,?)",
            (key, str(value))
        )


def is_owner(uid):
    return uid == OWNER_ID


def is_admin(uid):
    if is_owner(uid):
        return True
    with db() as con:
        return con.execute(
            "SELECT 1 FROM admins WHERE uid=?", (uid,)
        ).fetchone() is not None


def register_user(user):
    with db() as con:
        con.execute("""
        INSERT OR IGNORE INTO users(uid,username,joined)
        VALUES(?,?,?)
        """, (
            user.id,
            user.username or "",
            datetime.now().isoformat()
        ))
        con.execute(
            "UPDATE users SET username=? WHERE uid=?",
            (user.username or "", user.id)
        )


def banned(uid):
    with db() as con:
        row = con.execute(
            "SELECT banned FROM users WHERE uid=?", (uid,)
        ).fetchone()
        return bool(row["banned"]) if row else False


def premium(uid):
    if is_admin(uid):
        return True
    with db() as con:
        row = con.execute(
            "SELECT premium_until FROM users WHERE uid=?", (uid,)
        ).fetchone()

    if not row or not row["premium_until"]:
        return False

    try:
        return datetime.fromisoformat(
            row["premium_until"]
        ) > datetime.now()
    except ValueError:
        return False


def get_user_files(uid):
    with db() as con:
        return con.execute(
            "SELECT * FROM files WHERE uid=? ORDER BY id DESC",
            (uid,)
        ).fetchall()


def get_file(file_id):
    with db() as con:
        return con.execute(
            "SELECT * FROM files WHERE id=?", (file_id,)
        ).fetchone()


# ==========================================
# ACCESS CONTROL
# ==========================================

async def allowed(update, context):
    uid = update.effective_user.id

    if banned(uid):
        await update.effective_message.reply_text(
            "❌ You are banned from this bot."
        )
        return False

    if setting("locked") == "1" and not is_admin(uid):
        await update.effective_message.reply_text(
            "🔒 Bot is currently under maintenance."
        )
        return False

    channel = setting("channel")

    if channel and not is_admin(uid):
        try:
            member = await context.bot.get_chat_member(
                channel, uid
            )
            if member.status in ("left", "kicked"):
                await update.effective_message.reply_text(
                    f"📢 Please join {channel} first.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "Join Channel",
                            url=f"https://t.me/{channel.lstrip('@')}"
                        )
                    ]])
                )
                return False
        except Exception:
            log.exception("Channel membership check failed")
            await update.effective_message.reply_text(
                "Channel verification failed. Contact the owner."
            )
            return False

    return True


async def can_run(update):
    uid = update.effective_user.id

    if OWNER_ONLY_RUN and not is_owner(uid):
        await update.effective_message.reply_text(
            "⛔ Only the bot owner can execute scripts."
        )
        return False

    if not premium(uid) and not is_owner(uid):
        await update.effective_message.reply_text(
            "⭐ Premium subscription required to run scripts."
        )
        return False

    return True


# ==========================================
# KEYBOARD
# ==========================================

def main_keyboard(uid):
    buttons = [
        [
            InlineKeyboardButton("📤 Upload File", callback_data="upload"),
            InlineKeyboardButton("📁 Check Files", callback_data="files")
        ],
        [
            InlineKeyboardButton("⚡ Bot Speed", callback_data="speed"),
            InlineKeyboardButton("📊 Statistics", callback_data="stats")
        ],
        [
            InlineKeyboardButton("⭐ Subscriptions", callback_data="premium"),
            InlineKeyboardButton("▶ Running Code", callback_data="running")
        ],
        [
            InlineKeyboardButton("📢 Updates Channel", callback_data="channel"),
            InlineKeyboardButton("📞 Contact Owner", callback_data="contact")
        ],
        [
            InlineKeyboardButton("📖 Manual Install", callback_data="manual")
        ]
    ]

    if is_admin(uid):
        buttons.extend([
            [
                InlineKeyboardButton("🛠 Admin Panel", callback_data="admin"),
                InlineKeyboardButton("👥 Users", callback_data="users")
            ],
            [
                InlineKeyboardButton("📣 Broadcast", callback_data="broadcast"),
                InlineKeyboardButton("🔒 Lock Bot", callback_data="lock")
            ],
            [
                InlineKeyboardButton("⚙ Settings", callback_data="settings")
            ]
        ])

    return InlineKeyboardMarkup(buttons)


# ==========================================
# START
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)

    if not await allowed(update, context):
        return

    await update.message.reply_text(
        f"""
👋 Welcome to DARSHU BHAI HOSTING BOT

Hello {user.first_name}!

🚀 Python & JavaScript File Hosting

📂 Upload: .py / .js
▶ Run and manage scripts
📊 Statistics
⭐ Premium System
🛠 Admin Panel

👑 Owner: {OWNER_ID}
📞 Contact: {CONTACT_OWNER}
""",
        reply_markup=main_keyboard(user.id)
    )


# ==========================================
# UPLOAD FILE
# ==========================================

async def document_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    register_user(user)

    if not await allowed(update, context):
        return

    doc = update.message.document

    filename = Path(doc.file_name or "").name

    if not filename.endswith((".py", ".js")):
        await update.message.reply_text(
            "❌ Only .py and .js files are supported."
        )
        return

    if doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            "❌ Maximum file size is 5 MB."
        )
        return

    user_dir = BASE_DIR / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{int(time.time())}_{filename}"
    filepath = user_dir / safe_name

    try:
        telegram_file = await doc.get_file()
        await telegram_file.download_to_drive(filepath)

        with db() as con:
            cur = con.execute("""
            INSERT INTO files(uid,filename,path,created)
            VALUES(?,?,?,?)
            """, (
                user.id,
                filename,
                str(filepath),
                datetime.now().isoformat()
            ))
            file_id = cur.lastrowid

        await update.message.reply_text(
            f"""
<escape>✅</escape> File uploaded successfully!

🆔 File ID: `{file_id}`
📄 Name: {filename}
📦 Type: {filepath.suffix}

Use /files to manage your files.
Use /run {file_id} to start your script.
""",
            parse_mode="Markdown"
        )

    except Exception:
        log.exception("Upload failed")
        await update.message.reply_text(
            "❌ Upload failed. Please try again."
        )


# ==========================================
# FILE LIST
# ==========================================

async def files_command(update, context):
    if not await allowed(update, context):
        return

    rows = get_user_files(update.effective_user.id)

    if not rows:
        await update.message.reply_text("📂 No files uploaded.")
        return

    text = "📁 YOUR HOSTED FILES\n\n"

    for f in rows:
        text += (
            f"🆔 {f['id']} | {f['filename']}\n"
            f"▶ /run {f['id']}\n"
            f"⏹ /stop {f['id']}\n"
            f"🗑 /delete {f['id']}\n\n"
        )

    await update.message.reply_text(text)


def owns_file(uid, file_id):
    f = get_file(file_id)
    return f if f and (f["uid"] == uid or is_owner(uid)) else None


# ==========================================
# RUN PYTHON / JAVASCRIPT
# ==========================================

async def run_command(update, context):
    if not await allowed(update, context):
        return

    if not await can_run(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /run FILE_ID"
        )
        return

    try:
        file_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid file ID.")
        return

    f = owns_file(update.effective_user.id, file_id)

    if not f:
        await update.message.reply_text("File not found.")
        return

    if file_id in processes:
        await update.message.reply_text("⚠ Already running.")
        return

    path = Path(f["path"])

    if not path.is_file():
        await update.message.reply_text("File missing from server.")
        return

    if path.suffix == ".py":
        command = ["python", str(path)]
    elif path.suffix == ".js":
        command = ["node", str(path)]
    else:
        await update.message.reply_text("Unsupported file type.")
        return

    try:
        log_path = path.with_suffix(path.suffix + ".log")
        log_handle = open(log_path, "a", encoding="utf-8")

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(path.parent),
            stdout=log_handle,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True
        )

        processes[file_id] = {
            "process": process,
            "log": log_handle,
            "uid": f["uid"],
            "filename": f["filename"]
        }

        await update.message.reply_text(
            f"""
<escape>✅</escape> Script started!

🆔 ID: {file_id}
📄 File: {f['filename']}
⚙ PID: {process.pid}

Use /stop {file_id} to stop it.
Use /logs {file_id} to view logs.
"""
        )

    except FileNotFoundError:
        await update.message.reply_text(
            "Python or Node.js is not installed."
        )
    except Exception:
        log.exception("Script start failed")
        await update.message.reply_text("Failed to start script.")


# ==========================================
# STOP SCRIPT
# ==========================================

async def stop_process(file_id):
    info = processes.get(file_id)

    if not info:
        return False

    proc = info["process"]

    if proc.returncode is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()
        except ProcessLookupError:
            pass

    info["log"].close()
    processes.pop(file_id, None)
    return True


async def stop_command(update, context):
    if not await allowed(update, context):
        return

    if not context.args:
        await update.message.reply_text("Usage: /stop FILE_ID")
        return

    try:
        file_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid ID.")
        return

    info = processes.get(file_id)

    if not info or (
        info["uid"] != update.effective_user.id
        and not is_admin(update.effective_user.id)
    ):
        await update.message.reply_text("Script not found or unauthorized.")
        return

    if await stop_process(file_id):
        await update.message.reply_text("⏹ Script stopped.")
    else:
        await update.message.reply_text("Script is not running.")


# ==========================================
# LOGS
# ==========================================

async def logs_command(update, context):
    if not await allowed(update, context):
        return

    if not context.args:
        await update.message.reply_text("Usage: /logs FILE_ID")
        return

    try:
        file_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid ID.")
        return

    f = owns_file(update.effective_user.id, file_id)

    if not f:
        await update.message.reply_text("File not found.")
        return

    log_path = Path(f["path"] + ".log")

    if not log_path.exists():
        await update.message.reply_text("No logs available.")
        return

    content = log_path.read_text(
        encoding="utf-8", errors="replace"
    )[-3000:]

    await update.message.reply_text(
        "📋 LAST LOGS:\n\n" + (content or "Empty"),
    )


# ==========================================
# DELETE FILE
# ==========================================

async def delete_command(update, context):
    if not await allowed(update, context):
        return

    if not context.args:
        await update.message.reply_text("Usage: /delete FILE_ID")
        return

    try:
        file_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid ID.")
        return

    f = owns_file(update.effective_user.id, file_id)

    if not f:
        await update.message.reply_text("File not found.")
        return

    if file_id in processes:
        await update.message.reply_text(
            "Stop the script before deleting it."
        )
        return

    Path(f["path"]).unlink(missing_ok=True)
    Path(f["path"] + ".log").unlink(missing_ok=True)

    with db() as con:
        con.execute("DELETE FROM files WHERE id=?", (file_id,))

    await update.message.reply_text("🗑 File deleted successfully.")


# ==========================================
# RENAME
# ==========================================

async def rename_command(update, context):
    if not await allowed(update, context):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /rename FILE_ID newname.py"
        )
        return

    try:
        file_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid ID.")
        return

    new_name = Path(context.args[1]).name

    if not new_name.endswith((".py", ".js")):
        await update.message.reply_text("Only .py and .js allowed.")
        return

    f = owns_file(update.effective_user.id, file_id)

    if not f:
        await update.message.reply_text("File not found.")
        return

    if file_id in processes:
        await update.message.reply_text("Stop the script first.")
        return

    old_path = Path(f["path"])
    new_path = old_path.parent / f"{file_id}_{new_name}"

    if new_path.exists():
        await update.message.reply_text("Filename already exists.")
        return

    old_path.rename(new_path)

    with db() as con:
        con.execute(
            "UPDATE files SET filename=?,path=? WHERE id=?",
            (new_name, str(new_path), file_id)
        )

    await update.message.reply_text("✅ File renamed.")


# ==========================================
# RUNNING SCRIPTS
# ==========================================

async def running_command(update, context):
    if not await allowed(update, context):
        return

    uid = update.effective_user.id
    lines = ["▶ RUNNING SCRIPTS\n"]

    for fid, info in list(processes.items()):
        proc = info["process"]

        if proc.returncode is not None:
            await stop_process(fid)
            continue

        if info["uid"] == uid or is_admin(uid):
            lines.append(
                f"ID: {fid}\n"
                f"File: {info['filename']}\n"
                f"PID: {proc.pid}\n"
            )

    await update.message.reply_text(
        "\n".join(lines) if len(lines) > 1 else "No scripts running."
    )


# ==========================================
# STATISTICS / SPEED
# ==========================================

async def stats_command(update, context):
    if not await allowed(update, context):
        return

    with db() as con:
        users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        files = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        premium_users = con.execute(
            "SELECT COUNT(*) FROM users WHERE premium_until > ?",
            (datetime.now().isoformat(),)
        ).fetchone()[0]

    await update.message.reply_text(
        f"""
📊 DARSHU BHAI STATISTICS

👥 Total Users: {users}
📂 Total Files: {files}
⭐ Premium Users: {premium_users}
▶ Running Scripts: {len(processes)}
"""
    )


async def speed_command(update, context):
    start_time = time.monotonic()
    msg = await update.message.reply_text("Checking speed...")
    latency = (time.monotonic() - start_time) * 1000

    await msg.edit_text(
        f"⚡ Bot response time: {latency:.2f} ms"
    )


# ==========================================
# ADMIN PANEL
# ==========================================

async def admin_command(update, context):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Owner/admin only.")
        return

    await update.message.reply_text(
        """
🛠 DARSHU BHAI ADMIN PANEL

/premium USER_ID DAYS
/ban USER_ID
/unban USER_ID
/broadcast MESSAGE
/users
/addadmin USER_ID
/removeadmin USER_ID
/setchannel @channel
/lock on
/lock off
/stopall
"""
    )


async def premium_command(update, context):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("Owner only.")
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage: /premium USER_ID DAYS"
        )
        return

    try:
        uid, days = int(context.args[0]), int(context.args[1])
        if days < 1 or days > 3650:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Invalid user ID or days.")
        return

    expiry = (datetime.now() + timedelta(days=days)).isoformat()

    with db() as con:
        con.execute(
            "UPDATE users SET premium_until=? WHERE uid=?",
            (expiry, uid)
        )

    await update.message.reply_text(
        f"⭐ Premium updated for {uid} until {expiry}."
    )


async def ban_command(update, context):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban USER_ID")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    with db() as con:
        con.execute("UPDATE users SET banned=1 WHERE uid=?", (uid,))

    await update.message.reply_text(f"🚫 User {uid} banned.")


async def unban_command(update, context):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban USER_ID")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    with db() as con:
        con.execute("UPDATE users SET banned=0 WHERE uid=?", (uid,))

    await update.message.reply_text(f"✅ User {uid} unbanned.")


async def addadmin_command(update, context):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /addadmin USER_ID")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    with db() as con:
        con.execute("INSERT OR IGNORE INTO admins VALUES (?)", (uid,))

    await update.message.reply_text("Admin added.")


async def removeadmin_command(update, context):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /removeadmin USER_ID")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    with db() as con:
        con.execute("DELETE FROM admins WHERE uid=?", (uid,))

    await update.message.reply_text("Admin removed.")


async def users_command(update, context):
    if not is_admin(update.effective_user.id):
        return

    with db() as con:
        rows = con.execute(
            "SELECT uid,username,banned FROM users ORDER BY joined DESC LIMIT 50"
        ).fetchall()

    text = "👥 USERS (latest 50)\n\n"

    for row in rows:
        text += (
            f"{row['uid']} | @{row['username']} | "
            f"Banned: {row['banned']}\n"
        )

    await update.message.reply_text(text[:4000])


async def broadcast_command(update, context):
    if not is_owner(update.effective_user.id):
        return

    message = " ".join(context.args)

    if not message:
        await update.message.reply_text(
            "Usage: /broadcast Your message"
        )
        return

    with db() as con:
        rows = con.execute("SELECT uid FROM users").fetchall()

    sent = 0
    failed = 0

    for row in rows:
        try:
            await context.bot.send_message(
                row["uid"], message
            )
            sent += 1
        except Exception:
            failed += 1

        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"📣 Broadcast complete\nSent: {sent}\nFailed: {failed}"
    )


async def lock_command(update, context):
    if not is_owner(update.effective_user.id):
        return

    if not context.args or context.args[0] not in ("on", "off"):
        await update.message.reply_text("Usage: /lock on or /lock off")
        return

    set_setting("locked", "1" if context.args[0] == "on" else "0")

    await update.message.reply_text(
        f"Bot lock: {context.args[0].upper()}"
    )


async def setchannel_command(update, context):
    if not is_owner(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /setchannel @YourChannel\n"
            "Use /setchannel off to disable."
        )
        return

    channel = "" if context.args[0].lower() == "off" else context.args[0]

    if channel and not channel.startswith("@"):
        await update.message.reply_text("Use a public @channel username.")
        return

    set_setting("channel", channel)
    await update.message.reply_text(
        f"Updates channel set to: {channel or 'Disabled'}"
    )


async def stopall_command(update, context):
    if not is_owner(update.effective_user.id):
        return

    count = 0
    for fid in list(processes):
        if await stop_process(fid):
            count += 1

    await update.message.reply_text(
        f"⏹ Stopped {count} scripts."
    )


# ==========================================
# CALLBACK MENU
# ==========================================

async def callback_handler(update, context):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    data = query.data

    if data == "upload":
        await query.message.reply_text(
            "📤 Send your .py or .js file as a Telegram document."
        )

    elif data == "files":
        rows = get_user_files(uid)

        if not rows:
            await query.message.reply_text("No uploaded files.")
        else:
            text = "\n".join(
                f"ID {f['id']} — {f['filename']}"
                for f in rows
            )
            await query.message.reply_text(text)

    elif data == "speed":
        await query.message.reply_text(
            "⚡ Bot is online and responding."
        )

    elif data == "stats":
        with db() as con:
            users = con.execute(
                "SELECT COUNT(*) FROM users"
            ).fetchone()[0]
            files = con.execute(
                "SELECT COUNT(*) FROM files"
            ).fetchone()[0]

        await query.message.reply_text(
            f"📊 Users: {users}\nFiles: {files}\nRunning: {len(processes)}"
        )

    elif data == "premium":
        await query.message.reply_text(
            "⭐ PREMIUM SUBSCRIPTION\n\n"
            "Contact owner to activate premium:\n"
            + CONTACT_OWNER
        )

    elif data == "running":
        lines = []
        for fid, info in list(processes.items()):
            if info["uid"] == uid or is_admin(uid):
                if info["process"].returncode is None:
                    lines.append(
                        f"{fid} — {info['filename']}"
                    )

        await query.message.reply_text(
            "\n".join(lines) if lines else "No scripts running."
        )

    elif data == "channel":
        channel = setting("channel")
        await query.message.reply_text(
            f"📢 Updates Channel: {channel or 'Not configured'}"
        )

    elif data == "contact":
        await query.message.reply_text(
            f"📞 Contact Owner: {CONTACT_OWNER}"
        )

    elif data == "manual":
        await query.message.reply_text(
            "📖 MANUAL INSTALL\n\n"
            "1. Upload .py or .js file\n"
            "2. Use /files\n"
            "3. Use /run FILE_ID\n"
            "4. Use /logs FILE_ID\n"
            "5. Use /stop FILE_ID\n"
            "6. Use /delete FILE_ID"
        )

    elif data in ("admin", "users", "broadcast", "lock", "settings"):
        if not is_admin(uid):
            await query.message.reply_text("Admin only.")
            return

        if data == "admin":
            await query.message.reply_text(
                "Admin commands:\n"
                "/premium USER_ID DAYS\n"
                "/ban USER_ID\n"
                "/unban USER_ID\n"
                "/broadcast MESSAGE\n"
                "/users\n"
                "/addadmin USER_ID\n"
                "/removeadmin USER_ID\n"
                "/lock on/off\n"
                "/setchannel @channel\n"
                "/stopall"
            )

        elif data == "users":
            await users_command_from_callback(query, context)

        elif data == "broadcast":
            await query.message.reply_text(
                "Use /broadcast YOUR MESSAGE"
            )

        elif data == "lock":
            await query.message.reply_text(
                "Use /lock on or /lock off"
            )

        elif data == "settings":
            await query.message.reply_text(
                f"🔒 Locked: {setting('locked')}\n"
                f"📢 Channel: {setting('channel') or 'Off'}\n"
                f"Owner-only run: {OWNER_ONLY_RUN}"
            )


async def users_command_from_callback(query, context):
    with db() as con:
        rows = con.execute(
            "SELECT uid,username,banned FROM users LIMIT 50"
        ).fetchall()

    text = "👥 USERS\n\n"
    for r in rows:
        text += f"{r['uid']} | @{r['username']} | Ban: {r['banned']}\n"

    await query.message.reply_text(text[:4000])


# ==========================================
# ERROR HANDLER
# ==========================================

async def error_handler(update, context):
    log.error(
        "Telegram update error",
        exc_info=context.error
    )


# ==========================================
# MAIN
# ==========================================

def main():
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_BOT_TOKEN_HERE":
        raise RuntimeError(
            "Set BOT_TOKEN environment variable first."
        )

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("files", files_command))
    app.add_handler(CommandHandler("run", run_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("rename", rename_command))
    app.add_handler(CommandHandler("running", running_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("speed", speed_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("premium", premium_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("addadmin", addadmin_command))
    app.add_handler(CommandHandler("removeadmin", removeadmin_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("lock", lock_command))
    app.add_handler(CommandHandler("setchannel", setchannel_command))
    app.add_handler(CommandHandler("stopall", stopall_command))

    app.add_handler(
        MessageHandler(filters.Document.ALL, document_handler)
    )
    app.add_handler(
        CallbackQueryHandler(callback_handler)
    )

    app.add_error_handler(error_handler)

    print("================================")
    print(" DARSHU BHAI HOSTING BOT ONLINE")
    print("================================")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
