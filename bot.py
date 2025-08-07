import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from openai import OpenAI

# Загрузка .env переменных
load_dotenv()

# Логирование
logging.basicConfig(level=logging.INFO)

# Создаём клиента OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# /start команда
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я Spudnyk — твой AI-ассистент на базе GPT-4o. Напиши мне что-нибудь!")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # Вот здесь указана модель O4-mini (GPT-4o)
            messages=[
                {"role": "system", "content": "Ты — интеллектуальный AI-помощник по имени Spudnyk, созданный для помощи Ивану Овчаренко. Всегда отвечай ясно, профессионально и дружелюбно. Ты подключён к OpenAI и знаешь, что являешься моделью GPT-4o."},
                {"role": "user", "content": user_message},
            ]
        )
        reply = response.choices[0].message.content
        await update.message.reply_text(reply)

    except Exception as e:
        logging.error(f"Ошибка GPT: {e}")
        await update.message.reply_text("Произошла ошибка при обращении к GPT. Попробуй позже.")

# Основной запуск
async def main():
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        print("❌ TELEGRAM_BOT_TOKEN не найден")
        return

    app = ApplicationBuilder().token(telegram_token.strip()).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Бот запущен")
    await app.run_polling()

if __name__ == "__main__":
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        print("❌ TELEGRAM_BOT_TOKEN не найден")
        exit()

    app = ApplicationBuilder().token(telegram_token.strip()).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Бот запущен")
    app.run_polling()  # <-- запускается синхронно, без asyncio.run()