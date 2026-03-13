import os
import re
import requests
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from flask import Flask, request
from telegram.ext import (
    ApplicationBuilder,
    Dispatcher,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_KEY = os.getenv("TMDB_KEY")
OMDB_KEY = os.getenv("OMDB_KEY")
PORT = int(os.getenv("PORT", 5000))

app = Flask(__name__)
bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

# --- твои обработчики ---
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
bot_app.add_handler(CallbackQueryHandler(button_handler))

# --- endpoint для Telegram webhook ---
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    bot_app.update_queue.put(update)
    return "OK"

# --- при старте устанавливаем webhook ---
@app.before_first_request
def set_webhook():
    url = f"https://<твой-домен-на-render>/{BOT_TOKEN}"
    bot_app.bot.set_webhook(url)
    print("Webhook установлен на", url)

# --- запуск Flask ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

# ---------- SEARCH MOVIES ----------

def search_movies(query):

    url = "https://api.themoviedb.org/3/search/movie"

    params = {
        "api_key": TMDB_KEY,
        "query": query,
        "language": "ru-RU"
    }

    r = requests.get(url, params=params).json()

    results = []

    for movie in r.get("results", [])[:5]:

        year = ""

        if movie.get("release_date"):
            year = movie["release_date"][:4]

        results.append({
            "title": movie["title"],
            "year": year,
            "tmdb_id": movie["id"]
        })

    return results


# ---------- GET IMDB ID ----------

def get_imdb_id(tmdb_id):

    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"

    params = {
        "api_key": TMDB_KEY,
        "append_to_response": "external_ids"
    }

    r = requests.get(url, params=params).json()

    return r["external_ids"]["imdb_id"]


# ---------- GET RATINGS ----------

def get_ratings(imdb_id):

    url = "http://www.omdbapi.com/"

    params = {
        "apikey": OMDB_KEY,
        "i": imdb_id
    }

    r = requests.get(url, params=params).json()

    ratings = {}

    if r.get("imdbRating") and r["imdbRating"] != "N/A":
        ratings["imdb"] = float(r["imdbRating"])

    for item in r.get("Ratings", []):

        if item["Source"] == "Rotten Tomatoes":
            ratings["rt"] = int(item["Value"].replace("%", ""))

        if item["Source"] == "Metacritic":
            ratings["mc"] = int(item["Value"].split("/")[0])

    return ratings


# ---------- VERDICT ----------

def make_verdict(ratings):

    votes = []

    if "imdb" in ratings:
        votes.append(ratings["imdb"] >= 6)

    if "rt" in ratings:
        votes.append(ratings["rt"] >= 60)

    if "mc" in ratings:
        votes.append(ratings["mc"] >= 60)

    if not votes:
        return False

    return votes.count(True) > votes.count(False)


# ---------- FORMAT MESSAGE ----------

def format_message(title, year, ratings, verdict):

    text = f"🎬 {title} ({year})\n\n"

    if "imdb" in ratings:
        mark = "✅" if ratings["imdb"] >= 6 else "❌"
        text += f"IMDb: {ratings['imdb']} / 10 {mark}\n"

    if "rt" in ratings:
        mark = "✅" if ratings["rt"] >= 60 else "❌"
        text += f"Rotten Tomatoes: {ratings['rt']}% {mark}\n"

    if "mc" in ratings:
        mark = "✅" if ratings["mc"] >= 60 else "❌"
        text += f"Metacritic: {ratings['mc']} / 100 {mark}\n"

    text += "\n👁 Киноглаз Народа\n\n"

    if verdict:
        text += "Этот фильм стоит посмотреть"
    else:
        text += "Этот фильм не стоит просмотра"

    return text


# ---------- MESSAGE HANDLER ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.strip()

    # если это группа
    if update.message.chat.type != "private":

        m = re.match(r"(?i)^кг\s(.+)", text)

        if not m:
            return

        query = m.group(1)

    else:
        query = text

    movies = search_movies(query)

    if not movies:
        await update.message.reply_text("Фильм не найден.")
        return

    # если один фильм
    if len(movies) == 1:
        await process_movie(update, context, movies[0])
        return

    # если несколько — показываем кнопки
    keyboard = []

    for i, movie in enumerate(movies):

        title = f"{movie['title']} ({movie['year']})"

        keyboard.append([
            InlineKeyboardButton(title, callback_data=str(i))
        ])

    context.user_data["movies"] = movies

    await update.message.reply_text(
        "Я нашёл несколько фильмов:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------- PROCESS MOVIE ----------

async def process_movie(update, context, movie):

    imdb_id = get_imdb_id(movie["tmdb_id"])

    ratings = get_ratings(imdb_id)

    verdict = make_verdict(ratings)

    message = format_message(movie["title"], movie["year"], ratings, verdict)

    await update.message.reply_text(message)


# ---------- BUTTON HANDLER ----------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    movies = context.user_data.get("movies")

    if not movies:
        return

    index = int(query.data)

    movie = movies[index]

    await process_movie(query.message, context, movie)


# ---------- MAIN ----------

if __name__ == "__main__":
    print("Киноглаз Народа запущен 👁")
    app.run(host="0.0.0.0", port=PORT)

@app.before_first_request
def set_webhook():
    url = f"https://<твой-домен-на-render>/{BOT_TOKEN}"
    bot_app.bot.set_webhook(url)
    print("Webhook установлен на", url)
