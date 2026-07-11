import asyncio
import html
import io
import json
import logging
import os
import re

import requests
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    WebAppInfo,
    MenuButtonWebApp,
    FSInputFile,
)

from app import create_app, db
from app.models import TelegramUser
from datetime import datetime, date
from app.services import downloader_service

log = logging.getLogger('telegram_bot')

# flask_app is set by init_bot_webhook() at startup (webhook/production mode)
# or by the __main__ block (dev/polling mode). Declaring it here avoids
# NameError in _in_app_context while also breaking the circular-import:
# app/__init__.py → create_app() → imports telegram_bot → would call
# create_app() again at module level. Assigning None now is safe.
flask_app = None
dp = Dispatcher(storage=MemoryStorage())

# Persistent event loop for webhook mode (Gunicorn sync workers).
# asyncio.run() creates+closes a loop on every call, which kills aiohttp's
# pending timer callbacks with "Event loop is closed". A long-lived loop avoids this.
_webhook_loop = asyncio.new_event_loop()

MAX_UPLOAD_MB = 48          # Telegram bot uploads are capped at 50 MB
PAGE_BUTTONS_PER_ROW = 5
MAX_LISTED_ITEMS = 30       # keep list messages under Telegram's 4096 chars

ADMIN_ID = 364603275
CHANNELS_FILE = 'bot_channels.json'

POST_URL_RE = re.compile(
    r'instagram\.com/(?:[A-Za-z0-9._]+/)?(?:reel|reels|p|tv)/', re.IGNORECASE)
SHARE_URL_RE = re.compile(r'instagram\.com/share/', re.IGNORECASE)
PROFILE_URL_RE = re.compile(r'instagram\.com/@?(?P<u>[A-Za-z0-9._]+)/?', re.IGNORECASE)
USERNAME_RE = re.compile(r'[A-Za-z0-9._]{1,30}')
TIKTOK_RE = re.compile(r'(?:tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)', re.IGNORECASE)
YOUTUBE_RE = re.compile(r'(?:youtube\.com|youtu\.be)', re.IGNORECASE)

WEB_APP_URL = os.environ.get('WEB_APP_URL', 'https://instagram-mirolimov.uz/downloader')

TAB_LABELS = {'reels': '🎬 Reels', 'posts': '🖼 Posts', 'stories': '⏱ Stories'}

# chat_id -> {'username', 'tab', 'items': [...], 'cursor', 'has_more'}
sessions = {}

# ── Channels Storage ─────────────────────────────────────────────────────────

def load_channels():
    if not os.path.exists(CHANNELS_FILE):
        return []
    try:
        with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def save_channels(channels):
    with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

# ── FSM States ───────────────────────────────────────────────────────────────

class AdminStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_broadcast = State()


# ── Database Helpers for Telegram Users ──────────────────────────────────────

def db_save_telegram_user(chat_id, username, first_name, last_name):
    chat_id_str = str(chat_id)
    user = TelegramUser.query.filter_by(chat_id=chat_id_str).first()
    if not user:
        user = TelegramUser(
            chat_id=chat_id_str,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        db.session.add(user)
    else:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.is_blocked = False
    db.session.commit()

def db_get_telegram_users_stats():
    total = TelegramUser.query.count()
    active = TelegramUser.query.filter_by(is_blocked=False).count()
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_count = TelegramUser.query.filter(TelegramUser.created_at >= today_start).count()
    return {"total": total, "active": active, "today": today_count}

def db_get_all_active_telegram_user_ids():
    users = TelegramUser.query.filter_by(is_blocked=False).all()
    return [u.chat_id for u in users]

def db_mark_telegram_user_blocked(chat_id):
    chat_id_str = str(chat_id)
    user = TelegramUser.query.filter_by(chat_id=chat_id_str).first()
    if user:
        user.is_blocked = True
        db.session.commit()

# ── Middlewares ──────────────────────────────────────────────────────────────

class TrackUserMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get('event_from_user')
        if user:
            # Save or update user info in background thread
            await asyncio.to_thread(
                _in_app_context,
                db_save_telegram_user,
                chat_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
        return await handler(event, data)

class CheckSubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get('event_from_user')
        if not user:
            return await handler(event, data)
            
        if user.id == ADMIN_ID:
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == 'check_sub':
            return await handler(event, data)

        bot: Bot = data.get('bot')
        channels = load_channels()
        if not channels:
            return await handler(event, data)

        not_subscribed = []
        for ch in channels:
            try:
                member = await bot.get_chat_member(chat_id=ch['id'], user_id=user.id)
                if member.status in ['left', 'kicked', 'restricted']:
                    not_subscribed.append(ch)
            except TelegramForbiddenError:
                log.warning(f"Bot cannot access channel {ch['id']}")
            except Exception as e:
                log.warning(f"Membership check error on {ch['id']}: {e}")
                not_subscribed.append(ch)
                
        if not_subscribed:
            kb = []
            for ch in not_subscribed:
                kb.append([InlineKeyboardButton(text=ch.get('title', 'Kanal'), url=ch['url'])])
            kb.append([InlineKeyboardButton(text='✅ Tekshirish', callback_data='check_sub')])
            markup = InlineKeyboardMarkup(inline_keyboard=kb)
            
            text = "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak:</b>"
            if isinstance(event, Message):
                await event.answer(text, reply_markup=markup)
            elif isinstance(event, CallbackQuery):
                if event.data == 'check_sub':
                    await event.answer("Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)
                else:
                    await event.message.answer(text, reply_markup=markup)
                    await event.answer()
            return

        return await handler(event, data)

# Register TrackUserMiddleware first so users are always tracked
dp.message.outer_middleware(TrackUserMiddleware())
dp.callback_query.outer_middleware(TrackUserMiddleware())

dp.message.middleware(CheckSubscriptionMiddleware())
dp.callback_query.middleware(CheckSubscriptionMiddleware())


# ── Utilities ────────────────────────────────────────────────────────────────

def _in_app_context(fn, *args, **kwargs):
    if flask_app is None:
        raise RuntimeError('flask_app is not initialised — init_bot_webhook() was not called')
    with flask_app.app_context():
        return fn(*args, **kwargs)


async def run_service(fn, *args, **kwargs):
    """Run a blocking downloader_service call off the event loop."""
    return await asyncio.to_thread(_in_app_context, fn, *args, **kwargs)


def _fetch_bytes(url, max_mb=MAX_UPLOAD_MB):
    """Download a CDN file into memory, refusing anything over the bot limit."""
    limit = max_mb * 1024 * 1024
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        declared = int(resp.headers.get('Content-Length') or 0)
        if declared > limit:
            raise ValueError(
                f"Fayl juda katta ({declared // (1024 * 1024)} MB) — bot orqali "
                f"{max_mb} MB gacha yuborish mumkin. Saytdan yuklab oling.")
        buf = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            buf.write(chunk)
            if buf.tell() > limit:
                raise ValueError(
                    f"Fayl juda katta — bot orqali {max_mb} MB gacha yuborish "
                    "mumkin. Saytdan yuklab oling.")
        return buf.getvalue()


async def fetch_bytes(url):
    return await asyncio.to_thread(_fetch_bytes, url)


def fmt_count(n):
    if not n:
        return '0'
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace('.0M', 'M')
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace('.0K', 'K')
    return str(n)


def trim(text, limit):
    text = (text or '').replace('\n', ' ').strip()
    return text[:limit - 1] + '…' if len(text) > limit else text


async def safe_edit(message, text, reply_markup=None, **kwargs):
    """Edit a message, ignoring Telegram's 'message is not modified' error"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, **kwargs)
    except TelegramBadRequest as e:
        if 'message is not modified' not in str(e):
            raise

# ── Keyboards & list rendering ───────────────────────────────────────────────

def tabs_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, callback_data=f'tab:{tab}')
        for tab, label in TAB_LABELS.items()
    ]])


def item_icon(item):
    return {'video': '🎬', 'image': '🖼', 'carousel': f"📚{len(item.get('children') or [])}"}[item['type']]


def feed_text(session):
    lines = [f"<b>@{html.escape(session['username'])}</b> — {TAB_LABELS[session['tab']]}"]
    for i, item in enumerate(session['items'][:MAX_LISTED_ITEMS], start=1):
        parts = [f"{i}. {item_icon(item)}"]
        if item.get('play_count'):
            parts.append(f"▶️ {fmt_count(item['play_count'])}")
        if item.get('like_count'):
            parts.append(f"❤️ {fmt_count(item['like_count'])}")
        caption = trim(item.get('caption'), 40)
        if caption:
            parts.append(html.escape(caption))
        lines.append(' '.join(parts))
    lines.append("\nYuklab olish uchun raqamni bosing 👇")
    return '\n'.join(lines)


def feed_keyboard(session):
    count = min(len(session['items']), MAX_LISTED_ITEMS)
    rows = []
    for start in range(0, count, PAGE_BUTTONS_PER_ROW):
        rows.append([
            InlineKeyboardButton(text=str(i + 1), callback_data=f'it:{i}')
            for i in range(start, min(start + PAGE_BUTTONS_PER_ROW, count))
        ])
    nav = [InlineKeyboardButton(text='↩️ Bo\'limlar', callback_data='tabs')]
    if session.get('has_more') and session.get('cursor') and count < MAX_LISTED_ITEMS:
        nav.append(InlineKeyboardButton(text='➡️ Yana', callback_data='more'))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ── Media senders ────────────────────────────────────────────────────────────

async def send_video_from_url(message, video_url, filename, caption=None):
    await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
    data = await fetch_bytes(video_url)
    await message.answer_video(
        BufferedInputFile(data, filename=filename),
        caption=trim(caption, 900) or None)


async def send_photo_from_url(message, image_url, filename, caption=None):
    await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
    data = await fetch_bytes(image_url)
    await message.answer_photo(
        BufferedInputFile(data, filename=filename),
        caption=trim(caption, 900) or None)


async def send_carousel(message, item):
    """Send carousel children as Telegram albums (max 10 per album)."""
    children = [c for c in item.get('children') or []
                if c.get('video_url') or c.get('image_url')]
    if not children:
        raise ValueError("Bu postda yuklab olinadigan media topilmadi.")
    await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
    name = item.get('code') or 'media'
    media = []
    for i, child in enumerate(children, start=1):
        if child.get('video_url'):
            data = await fetch_bytes(child['video_url'])
            media.append(InputMediaVideo(
                media=BufferedInputFile(data, filename=f"instagram_{name}_{i}.mp4")))
        else:
            data = await fetch_bytes(child['image_url'])
            media.append(InputMediaPhoto(
                media=BufferedInputFile(data, filename=f"instagram_{name}_{i}.jpg")))
    caption = trim(item.get('caption'), 900)
    if caption:
        media[0].caption = caption
    for start in range(0, len(media), 10):
        await message.answer_media_group(media[start:start + 10])


async def send_item(message, item):
    name = item.get('code') or item.get('id') or 'media'
    caption = item.get('caption')
    if item['type'] == 'carousel':
        await send_carousel(message, item)
    elif item['type'] == 'image':
        if not item.get('image_url'):
            raise ValueError("Bu rasm uchun yuklab olish havolasi topilmadi.")
        await send_photo_from_url(message, item['image_url'],
                                  f"instagram_{name}.jpg", caption)
    else:  # video — listing may or may not carry a direct URL
        video_url = item.get('video_url')
        if not video_url:
            info = await run_service(downloader_service.resolve_download,
                                     item['post_url'])
            video_url = info['video_url']
            caption = caption or info.get('title')
        await send_video_from_url(message, video_url,
                                  f"instagram_{name}.mp4", caption)

# ── Handlers ─────────────────────────────────────────────────────────────────

WELCOME = (
    "Salom! 👋 Men Instagram, TikTok va YouTube qisqa videolarini yuklovchi botman.\n\n"
    "📎 <b>Instagram Reel, TikTok yoki YouTube havolasini</b> yuboring — videoni suv belgisiz yuklab beraman.\n"
    "👤 <b>Username</b> yuboring (@ bilan yoki @siz) — Instagram profildagi reels, postlar va "
    "storylarini ko'rsataman.\n\n"
    "Misol: <code>aytishnik.uz</code> yoki <code>https://vt.tiktok.com/...</code>"
)


@dp.message(CommandStart())
@dp.message(Command('help'))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Mini Appni ochish", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    await message.answer(WELCOME, reply_markup=kb)


@dp.message(Command('about'))
async def cmd_about(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Mini Appni ochish", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    
    # Fayl ID ni .env dan olamiz
    file_id = os.environ.get('ABOUT_VIDEO_FILE_ID')
    if flask_app:
        file_id = flask_app.config.get('ABOUT_VIDEO_FILE_ID') or file_id
        
    if file_id:
        await message.answer_video(file_id, caption=WELCOME, reply_markup=kb)
        return

    video_path = os.path.join('app', 'static', 'video', 'instasaveme.mp4')
    if os.path.exists(video_path):
        video = FSInputFile(video_path)
        await message.answer_video(video, caption=WELCOME, reply_markup=kb)
    else:
        # Agar video topilmasa, oddiy text jo'natiladi
        await message.answer(WELCOME, reply_markup=kb)


@dp.callback_query(F.data == 'check_sub')
async def on_check_sub(callback: CallbackQuery):
    # Agar middleware'dan o'tib kelsa, demak barcha kanallarga obuna bo'lgan.
    await callback.message.delete()
    await callback.answer("✅ Obuna tasdiqlandi! Rahmat.")
    await callback.message.answer("Endi botdan bemalol foydalanishingiz mumkin. \n\nYordam uchun /help bosing.")


# ── Admin Handlers ───────────────────────────────────────────────────────────

@dp.message(Command('admin'), F.from_user.id == ADMIN_ID)
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    kb = [
        [InlineKeyboardButton(text="📋 Kanallarni ko'rish", callback_data="admin:list")],
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="admin:add")],
        [InlineKeyboardButton(text="➖ Kanalni o'chirish", callback_data="admin:del")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar soni", callback_data="admin:users_count")],
        [InlineKeyboardButton(text="📣 Reklama yuborish", callback_data="admin:broadcast")]
    ]
    await message.answer("👑 <b>Admin Panel</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@dp.callback_query(F.data.startswith('admin:'), F.from_user.id == ADMIN_ID)
async def on_admin_action(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(':')[1]
    
    if action == 'list':
        channels = load_channels()
        if not channels:
            await callback.message.edit_text("Hozircha majburiy kanallar yo'q.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin:back")]]))
            return
        
        text = "📋 <b>Majburiy kanallar:</b>\n\n"
        for i, ch in enumerate(channels, 1):
            text += f"{i}. <a href='{ch['url']}'>{html.escape(ch.get('title', 'Kanal'))}</a> (ID: <code>{ch['id']}</code>)\n"
        await callback.message.edit_text(text, disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin:back")]]))

    elif action == 'add':
        await callback.message.edit_text("➕ Yangi kanal qo'shish uchun kanaldan biron bir xabarni menga forward (uzatish) qiling yoki kanal ID sini (-100... bilan) va havolasini yuboring (Masalan: <code>-1001234567890 https://t.me/kanal</code>). Bot o'sha kanalda admin bo'lishi shart!", 
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin:back")]]))
        await state.set_state(AdminStates.waiting_for_channel)

    elif action == 'del':
        channels = load_channels()
        if not channels:
            await callback.message.edit_text("Hozircha majburiy kanallar yo'q.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin:back")]]))
            return
            
        kb = []
        for ch in channels:
            kb.append([InlineKeyboardButton(text=f"❌ {ch.get('title', 'Kanal')} ({ch['id']})", callback_data=f"admin:rm:{ch['id']}")])
        kb.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin:back")])
        await callback.message.edit_text("O'chirmoqchi bo'lgan kanalni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        
    elif action.startswith('rm:'):
        ch_id = action.split(':', 1)[1]
        channels = load_channels()
        channels = [c for c in channels if str(c['id']) != str(ch_id)]
        save_channels(channels)
        await callback.answer("Kanal o'chirildi!", show_alert=True)
        # Refresh the delete list
        kb = []
        for ch in channels:
            kb.append([InlineKeyboardButton(text=f"❌ {ch.get('title', 'Kanal')} ({ch['id']})", callback_data=f"admin:rm:{ch['id']}")])
        kb.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin:back")])
        text = "O'chirmoqchi bo'lgan kanalni tanlang:" if channels else "Kanallar qolmadi."
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        
    elif action == 'users_count':
        stats = await asyncio.to_thread(_in_app_context, db_get_telegram_users_stats)
        text = (
            f"👥 <b>Bot foydalanuvchilari statistikasi:</b>\n\n"
            f"📈 Jami a'zolar: {stats['total']}\n"
            f"🟢 Faol a'zolar (bloklamagan): {stats['active']}\n"
            f"📅 Bugun qo'shilganlar: {stats['today']}"
        )
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin:back")]]))

    elif action == 'broadcast':
        await callback.message.edit_text("📣 <b>Reklama yuborish bo'limi</b>\n\n"
                                         "Iltimos, reklama xabarini yuboring. Bu matn, rasm, video, audio yoki boshqa turdagi post bo'lishi mumkin. "
                                         "Bot barcha faol foydalanuvchilarga ushbu xabarni nusxalab yuboradi.",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin:back")]]))
        await state.set_state(AdminStates.waiting_for_broadcast)

    elif action == 'back':
        await state.clear()
        kb = [
            [InlineKeyboardButton(text="📋 Kanallarni ko'rish", callback_data="admin:list")],
            [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="admin:add")],
            [InlineKeyboardButton(text="➖ Kanalni o'chirish", callback_data="admin:del")],
            [InlineKeyboardButton(text="👥 Foydalanuvchilar soni", callback_data="admin:users_count")],
            [InlineKeyboardButton(text="📣 Reklama yuborish", callback_data="admin:broadcast")]
        ]
        await callback.message.edit_text("👑 <b>Admin Panel</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))



@dp.message(AdminStates.waiting_for_channel, F.from_user.id == ADMIN_ID)
async def on_channel_info_received(message: Message, state: FSMContext):
    chat_id = None
    url = None
    
    if message.forward_from_chat:
        chat = message.forward_from_chat
        chat_id = str(chat.id)
        if chat.username:
            url = f"https://t.me/{chat.username}"
        else:
            await message.answer("Yopiq kanal ekan. Iltimos, quyidagi formatda yuboring: \n<code>ID https://t.me/invite_link</code>")
            return
    else:
        parts = message.text.split()
        if len(parts) >= 2:
            chat_id = parts[0]
            url = parts[1]
        else:
            await message.answer("Xato format. Qaytadan yuboring yoki bekor qiling.")
            return

    try:
        chat = await message.bot.get_chat(chat_id)
        title = chat.title or "Kanal"
        if not url and chat.username:
            url = f"https://t.me/{chat.username}"
            
        channels = load_channels()
        if any(c['id'] == str(chat_id) for c in channels):
            await message.answer("Bu kanal allaqachon qo'shilgan.")
        else:
            channels.append({"id": str(chat_id), "url": url, "title": title})
            save_channels(channels)
            await message.answer(f"✅ Kanal muvaffaqiyatli qo'shildi!\n\nNomi: {title}\nID: {chat_id}")
    except TelegramBadRequest as e:
         await message.answer(f"Xato: Kanal topilmadi yoki bot u yerda admin emas. ({e})")
    except Exception as e:
         await message.answer(f"Kutilmagan xato: {e}")
         
    await state.clear()
    await cmd_admin(message, state) # show admin panel again


@dp.message(AdminStates.waiting_for_broadcast, F.from_user.id == ADMIN_ID)
async def on_broadcast_received(message: Message, state: FSMContext):
    await state.clear()
    status_msg = await message.answer("⏳ Reklama yuborilmoqda, iltimos kuting...")
    
    user_ids = await asyncio.to_thread(_in_app_context, db_get_all_active_telegram_user_ids)
    if not user_ids:
        await status_msg.edit_text("⚠️ Botda faol foydalanuvchilar topilmadi.")
        await cmd_admin(message, state)
        return
        
    success = 0
    failed = 0
    blocked = 0
    
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=int(uid))
            success += 1
            await asyncio.sleep(0.05) # anti-flood delay
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            blocked += 1
            await asyncio.to_thread(_in_app_context, db_mark_telegram_user_blocked, uid)
        except Exception as e:
            log.warning(f"Failed to send broadcast to {uid}: {e}")
            failed += 1
            
    text = (
        f"✅ <b>Reklama yuborish yakunlandi!</b>\n\n"
        f"👤 Jami yuborilgan: {len(user_ids)}\n"
        f"🎉 Muvaffaqiyatli: {success}\n"
        f"🚫 Bloklaganlar: {blocked}\n"
        f"⚠️ Xatoliklar: {failed}"
    )
    await status_msg.edit_text(text)
    await cmd_admin(message, state)


# ── Main User Handlers ───────────────────────────────────────────────────────

@dp.message(F.text)
async def on_text(message: Message, state: FSMContext):
    await state.clear()
    text = (message.text or '').strip()

    is_insta = POST_URL_RE.search(text) or SHARE_URL_RE.search(text)
    is_tiktok = TIKTOK_RE.search(text)
    is_youtube = YOUTUBE_RE.search(text)

    if is_insta or is_tiktok or is_youtube:
        status = await message.answer('⏳ Yuklanmoqda…')
        try:
            info = await run_service(downloader_service.resolve_download, text)
            await send_video_from_url(
                message, info['video_url'], info['filename'],
                caption=info.get('title'))
            await status.delete()
        except ValueError as e:
            await status.edit_text(f"⚠️ {html.escape(str(e))}")
        except Exception:
            log.exception('URL download failed')
            await status.edit_text("⚠️ Yuklab bo'lmadi. Keyinroq urinib ko'ring.")
        return

    profile = PROFILE_URL_RE.search(text)
    username = profile.group('u') if profile else re.sub(r'^[@\s]+', '', text)
    if not USERNAME_RE.fullmatch(username):
        await message.answer(
            "Username yoki Instagram havolasini yuboring. Yordam: /help")
        return

    if len(sessions) > 1000:  # avoid unbounded growth on a long-lived process
        sessions.clear()
    sessions[message.chat.id] = {'username': username.lower()}
    await message.answer(
        f"<b>@{html.escape(username.lower())}</b> — nimani yuklaymiz?",
        reply_markup=tabs_keyboard())


async def load_feed(session, tab, cursor=''):
    if tab == 'stories':
        payload = await run_service(downloader_service.fetch_stories,
                                    session['username'])
    else:
        fetch = (downloader_service.fetch_reels if tab == 'reels'
                 else downloader_service.fetch_posts)
        payload = await run_service(fetch, session['username'], cursor)
    session['tab'] = tab
    session.setdefault('items', [])
    if cursor:
        session['items'].extend(payload['items'])
    else:
        session['items'] = payload['items']
    session['cursor'] = payload.get('next_max_id')
    session['has_more'] = bool(payload.get('has_more'))
    return payload


@dp.callback_query(F.data == 'tabs')
async def on_tabs(callback: CallbackQuery):
    session = sessions.get(callback.message.chat.id)
    if not session:
        await callback.answer('Avval username yuboring.', show_alert=True)
        return
    await safe_edit(callback.message,
                    f"<b>@{html.escape(session['username'])}</b> — nimani yuklaymiz?",
                    reply_markup=tabs_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith('tab:') | (F.data == 'more'))
async def on_tab(callback: CallbackQuery):
    session = sessions.get(callback.message.chat.id)
    if not session:
        await callback.answer('Avval username yuboring.', show_alert=True)
        return

    more = callback.data == 'more'
    tab = session.get('tab') if more else callback.data.split(':', 1)[1]
    cursor = (session.get('cursor') or '') if more else ''
    if more and not cursor:
        await callback.answer('Boshqa media yo\'q.')
        return

    await callback.answer('⏳')
    try:
        await load_feed(session, tab, cursor)
    except ValueError as e:
        await safe_edit(callback.message,
                        f"⚠️ {html.escape(str(e))}", reply_markup=tabs_keyboard())
        return
    except Exception:
        log.exception('feed load failed')
        await safe_edit(callback.message,
                        "⚠️ Xatolik yuz berdi. Keyinroq urinib ko'ring.",
                        reply_markup=tabs_keyboard())
        return

    if not session['items']:
        note = ("Hozir aktiv story yo'q — storylar 24 soatdan keyin yo'qoladi."
                if tab == 'stories' else 'Bu bo\'limda hech narsa topilmadi.')
        await safe_edit(callback.message,
                        f"<b>@{html.escape(session['username'])}</b> — {TAB_LABELS[tab]}\n\n{note}",
                        reply_markup=tabs_keyboard())
        return

    await safe_edit(callback.message,
                    feed_text(session), reply_markup=feed_keyboard(session),
                    disable_web_page_preview=True)


@dp.callback_query(F.data.startswith('it:'))
async def on_item(callback: CallbackQuery):
    session = sessions.get(callback.message.chat.id)
    idx = int(callback.data.split(':', 1)[1])
    items = (session or {}).get('items') or []
    if idx >= len(items):
        await callback.answer('Ro\'yxat eskirgan — username qayta yuboring.',
                              show_alert=True)
        return

    await callback.answer('⬇️ Yuklanmoqda…')
    try:
        await send_item(callback.message, items[idx])
    except ValueError as e:
        await callback.message.answer(f"⚠️ {html.escape(str(e))}")
    except Exception:
        log.exception('item send failed')
        await callback.message.answer(
            "⚠️ Yuborib bo'lmadi. Media juda katta yoki havola eskirgan "
            "bo'lishi mumkin.")


# ── Webhook mode (Railway/production) ───────────────────────────────────────
# Bot Telegram webhook orqali Flask ichida ishlaydi.
# Bu Railway'da cold-start muammosini bartaraf etadi.

def register_webhook_routes(flask_application, bot_instance: 'Bot'):
    """Flask app ga /webhook/<token> endpoint qo'shadi."""
    from aiogram.types import Update
    from flask import request as flask_request, Response

    token = flask_application.config.get('TELEGRAM_BOT_TOKEN', '')
    secret = token.split(':')[0]  # bot ID ni secret path sifatida ishlatamiz

    @flask_application.route(f'/webhook/{secret}', methods=['POST'])
    def telegram_webhook():
        try:
            data = flask_request.get_json(force=True)
            update = Update.model_validate(data)
            # Gunicorn sync worker uchun doimiy event loop ishlatamiz.
            # asyncio.run() loopni yopib yuboradi va aiohttp callback'larini
            # "Event loop is closed" xatosi bilan ishdan chiqaradi.
            _webhook_loop.run_until_complete(dp.feed_update(bot_instance, update))
        except Exception:
            log.exception('Webhook update processing error')
        return Response('ok', status=200)

    log.info(f'Webhook endpoint registered at /webhook/{secret}')
    return f'/webhook/{secret}'


async def setup_bot_webhook(bot_instance: 'Bot', webhook_url: str):
    """Telegram API ga webhook URL ni ro'yxatdan o'tkazadi."""
    await bot_instance.set_webhook(
        url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types(),
    )
    log.info(f'Webhook set: {webhook_url}')

    # Set Menu Button for Web App
    try:
        await bot_instance.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Mini App",
                web_app=WebAppInfo(url=WEB_APP_URL)
            )
        )
    except Exception as e:
        log.warning(f'Could not set menu button: {e}')


def init_bot_webhook(flask_application):
    """Bot ni webhook rejimida ishga tushiradi (Flask startup da chaqiriladi)."""
    global flask_app
    flask_app = flask_application  # make it available to _in_app_context et al.

    token = flask_application.config.get('TELEGRAM_BOT_TOKEN')
    if not token:
        log.warning(
            'TELEGRAM_BOT_TOKEN topilmadi — bot webhook rejimida ishlamaydi.')
        return

    webhook_host = flask_application.config.get(
        'WEBHOOK_HOST',
        os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
    )
    if not webhook_host:
        log.warning(
            'WEBHOOK_HOST yoki RAILWAY_PUBLIC_DOMAIN topilmadi — '
            'bot polling rejimida ishga tushadi.')
        asyncio.run(_run_polling(token))
        return

    if not webhook_host.startswith('https://'):
        webhook_host = f'https://{webhook_host}'

    bot_instance = Bot(
        token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    path = register_webhook_routes(flask_application, bot_instance)
    webhook_url = f'{webhook_host.rstrip("/")}{path}'

    # Webhook ni async tarzda ro'yxatdan o'tkazish
    try:
        # We must use the persistent _webhook_loop here. If we create a temporary
        # loop and close it, bot_instance's aiohttp session will be bound to
        # the closed loop, causing "Event loop is closed" errors later.
        _webhook_loop.run_until_complete(setup_bot_webhook(bot_instance, webhook_url))
    except Exception:
        log.exception('Webhook registration failed')


async def _run_polling(token: str):
    """Fallback: development uchun long-polling rejimi."""
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Mini App",
                web_app=WebAppInfo(url=WEB_APP_URL)
            )
        )
    except Exception as e:
        log.warning(f'Could not set menu button: {e}')
    log.info('Bot is starting (long polling fallback)…')
    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    # Dev environment: polling rejimida ishga tushir
    # Create the Flask app here (avoids circular import at module level)
    flask_app = create_app('config.Config')
    token = flask_app.config.get('TELEGRAM_BOT_TOKEN')
    if token:
        asyncio.run(_run_polling(token))
    else:
        raise SystemExit(
            'TELEGRAM_BOT_TOKEN topilmadi. @BotFather dan token oling va '
            '.env fayliga TELEGRAM_BOT_TOKEN=... qatorini qo\'shing.')
