#!/usr/bin/env python3
import os
import logging
from functools import wraps
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.utils.helpers import escape_markdown
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext
)
from requests.exceptions import ReadTimeout

import hianimez_scraper
from hianimez_scraper import (
    search_anime, get_episodes_list, extract_episode_stream_and_subtitle
)
from utils import download_and_rename_subtitle

# ——————————————————————————————————————————
# 1) Load & validate env
# ——————————————————————————————————————————
load_dotenv()
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
ANIWATCH_API_BASE = os.getenv("ANIWATCH_API_BASE")
if not TELEGRAM_TOKEN or not ANIWATCH_API_BASE:
    raise RuntimeError("Missing TELEGRAM_TOKEN or ANIWATCH_API_BASE in .env")

# inject into scraper
hianimez_scraper.ANIWATCH_API_BASE = ANIWATCH_API_BASE

# ——————————————————————————————————————————
# 2) Logging + Bot init
# ——————————————————————————————————————————
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

updater    = Updater(TELEGRAM_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# ——————————————————————————————————————————
# 3) Auth decorator
# ——————————————————————————————————————————
AUTHORIZED_USERS = {1423807625, 5476335536, 2096201372, 633599652}
def restricted(fn):
    @wraps(fn)
    def wrapped(update: Update, ctx: CallbackContext, *a, **k):
        if update.effective_user.id not in AUTHORIZED_USERS:
            return ctx.bot.send_message(update.effective_chat.id, "🚫 Access denied")
        return fn(update, ctx, *a, **k)
    return wrapped

# ——————————————————————————————————————————
# 4) Caches
# ——————————————————————————————————————————
search_cache  = {}  # chat_id -> list of (title, slug)
episode_cache = {}  # chat_id -> list of (ep_num, ep_id)

# ——————————————————————————————————————————
# 5) /start
# ——————————————————————————————————————————
@restricted
def start(update: Update, ctx: CallbackContext):
    update.message.reply_text("Welcome! Use /search <anime> to begin.")

# ——————————————————————————————————————————
# 6) /search
# ——————————————————————————————————————————
@restricted
def search_command(update: Update, ctx: CallbackContext):
    if not ctx.args:
        return update.message.reply_text("Usage: /search <anime_name>")
    query = " ".join(ctx.args)
    msg   = update.message.reply_text(f"Searching for {query}…")
    try:
        results = search_anime(query)
    except Exception as e:
        logger.exception("Search failed")
        return msg.edit_text("Search failed.")
    if not results:
        return msg.edit_text("No results.")
    chat_id = update.effective_chat.id
    search_cache[chat_id] = [(t, s) for t, _, s in results]
    buttons = [
        [InlineKeyboardButton(t, callback_data=f"anime_idx:{i}")]
        for i, (t, _) in enumerate(search_cache[chat_id])
    ]
    msg.edit_text("Select anime:", reply_markup=InlineKeyboardMarkup(buttons))

# ——————————————————————————————————————————
# 7) anime_idx callback
# ——————————————————————————————————————————
@restricted
def anime_callback(update: Update, ctx: CallbackContext):
    query   = update.callback_query; query.answer()
    chat_id = query.message.chat.id
    idx     = int(query.data.split(":",1)[1])
    title, slug = search_cache[chat_id][idx]
    ctx.user_data["anime_title"] = title
    query.edit_message_text(f"Fetching episodes for {title}…")

    episodes = get_episodes_list(slug)
    episode_cache[chat_id] = episodes

    buttons = [
        [InlineKeyboardButton(f"Episode {num}", callback_data=f"episode_idx:{i}")]
        for i, (num, _) in enumerate(episodes)
    ]
    buttons.append([InlineKeyboardButton("Download All", callback_data="episode_all")])
    query.edit_message_text(
        "Select episode:", reply_markup=InlineKeyboardMarkup(buttons)
    )

# ――――――――――――――――――――――――――――――――――――――
# 8) episode_idx callback
# ――――――――――――――――――――――――――――――――――――――
@restricted
def episode_callback(update: Update, ctx: CallbackContext):
    query   = update.callback_query; query.answer()
    chat_id = query.message.chat.id
    i = int(query.data.split(":",1)[1])
    ep_num, ep_id = episode_cache[chat_id][i]
    title = ctx.user_data.get("anime_title", "Unknown")
    query.message.reply_text(f"{title} — Episode {ep_num}")

    try:
        hls, sub_url = extract_episode_stream_and_subtitle(ep_id)
    except Exception:
        return ctx.bot.send_message(chat_id, "⚠️ Could not fetch stream.")

    if not hls:
        return ctx.bot.send_message(chat_id, "⚠️ Stream not available.")

    link = escape_markdown(hls, version=2)
    ctx.bot.send_message(chat_id, f"HLS: `{link}`", parse_mode="MarkdownV2")

    # subtitles
    cache = os.path.join("subs", str(chat_id))
    os.makedirs(cache, exist_ok=True)
    try:
        local = download_and_rename_subtitle(sub_url, ep_num, cache)
        with open(local,"rb") as f:
            ctx.bot.send_document(chat_id, document=InputFile(f), caption="Subtitle")
    except Exception:
        ctx.bot.send_message(chat_id, "⚠️ Subtitle not available.")

# ――――――――――――――――――――――――――――――――――――――
# 9) Download All
# ――――――――――――――――――――――――――――――――――――――
@restricted
def episodes_all_callback(update: Update, ctx: CallbackContext):
    query   = update.callback_query; query.answer()
    chat_id = query.message.chat.id
    eps = episode_cache.get(chat_id, [])
    if not eps:
        return query.edit_message_text("Nothing to download.")
    query.delete_message()
    for num, ep_id in eps:
        try:
            hls, sub_url = extract_episode_stream_and_subtitle(ep_id)
        except:
            continue
        if hls:
            link = escape_markdown(hls, version=2)
            ctx.bot.send_message(chat_id, f"Episode {num}: `{link}`", parse_mode="MarkdownV2")
        # skip subtitles here for brevity

# ――――――――――――――――――――――――――――――――――――――
# 10) Error handler & register
# ――――――――――――――――――――――――――――――――――――――
def error_handler(update, ctx):
    logger.error("Update error", exc_info=ctx.error)

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("search", search_command))
dispatcher.add_handler(CallbackQueryHandler(anime_callback, pattern=r"^anime_idx:"))
dispatcher.add_handler(CallbackQueryHandler(episode_callback, pattern=r"^episode_idx:"))
dispatcher.add_handler(CallbackQueryHandler(episodes_all_callback, pattern=r"^episode_all$"))
dispatcher.add_error_handler(error_handler)

if __name__ == "__main__":
    updater.start_polling()
    updater.idle()
