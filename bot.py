import logging
import os
import re
import language_tool_python
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан")

MAX_TEXT_LENGTH = 5000

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== ИНИЦИАЛИЗАЦИЯ LanguageTool (публичное API, без Java) ==========
try:
    tool = language_tool_python.LanguageToolPublicAPI("ru-RU")
    logger.info("LanguageToolPublicAPI инициализирован для русского языка")
except Exception as e:
    logger.error(f"Ошибка: {e}")
    tool = None

# ========== КЛАВИАТУРЫ ==========
async def start_keyboard():
    keyboard = [
        [InlineKeyboardButton("📖 Помощь", callback_data="help")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== КОМАНДЫ ==========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для проверки орфографии и грамматики.\n\n"
        "📝 Просто отправь текст на русском языке, и я найду ошибки.\n\n"
        "⚡️ Бесплатно, без подписок и без Java!",
        reply_markup=await start_keyboard(),
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Как пользоваться:*\n\n"
        "1️⃣ Отправь текст на русском (до 5000 символов).\n"
        "2️⃣ Я покажу ошибки и варианты исправлений.\n\n"
        "🔧 Команды:\n"
        "/start — приветствие\n"
        "/help — помощь\n"
        "/about — о боте",
        parse_mode="Markdown"
    )

async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *О боте*\n\n"
        "Использую публичный API LanguageTool — мощный инструмент проверки грамматики.\n"
        "Бот не сохраняет ваши тексты.\n\n"
        "Работает без Java, без установки дополнительных программ.",
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "help":
        await query.edit_message_text(
            "📖 Отправьте текст, и я найду ошибки. До 5000 символов.",
            reply_markup=await start_keyboard(),
        )
    elif query.data == "about":
        await query.edit_message_text(
            "ℹ️ Бесплатный бот на базе LanguageToolPublicAPI. Без сохранения текстов.",
            reply_markup=await start_keyboard(),
        )

# ========== ОСНОВНАЯ ЛОГИКА ==========
def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    text = ''.join(ch for ch in text if ord(ch) >= 32 or ch in '\n\r')
    return text.strip()

async def check_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Асинхронно проверяет текст и отправляет результат"""
    user_text = update.message.text
    if user_text.startswith('/'):
        return

    if len(user_text) > MAX_TEXT_LENGTH:
        await update.message.reply_text(f"⚠️ Текст слишком длинный ({len(user_text)} символов). Максимум {MAX_TEXT_LENGTH}.")
        return

    processing_msg = await update.message.reply_text("🔍 Проверяю текст...")

    text = clean_text(user_text)
    if not text:
        await processing_msg.delete()
        await update.message.reply_text("❌ Текст не содержит значимых символов.")
        return

    if not tool:
        await processing_msg.delete()
        await update.message.reply_text("❌ Сервис проверки временно недоступен. Попробуйте позже.")
        return

    try:
        # Запускаем проверку синхронно, т.к. метод не async
        matches = tool.check(text)

        if not matches:
            await update.message.reply_text("✅ Ошибок не найдено!")
            await processing_msg.delete()
            return

        result_parts = []
        for i, match in enumerate(matches[:30]):
            error_type = "🔤 Орфография" if "SPELLING" in str(match.ruleId) else "📐 Грамматика"
            # Безопасно получаем слово с ошибкой
            start = match.offset
            end = match.offset + match.errorLength
            error_word = text[start:end] if start < len(text) else match.context
            context_clean = match.context.replace('`', '')

            correction_text = ""
            if match.replacements:
                repl = ", ".join(match.replacements[:5])
                correction_text = f"➜ *Варианты:* {repl}"

            error_msg = (
                f"{i+1}. **{error_type}**\n"
                f"📝 Ошибка: `{error_word}`\n"
                f"📖 Контекст: {context_clean}\n"
                f"{correction_text}"
            )
            result_parts.append(error_msg)

        if len(matches) > 30:
            result_parts.append(f"\n... и ещё {len(matches)-30} ошибок.")

        final_message = "\n\n".join(result_parts)
        # Разбиваем на части, если длиннее 4096
        for i in range(0, len(final_message), 4096):
            await update.message.reply_text(final_message[i:i+4096], parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка при проверке: {e}")
        await update.message.reply_text("❌ Произошла ошибка при проверке текста. Попробуйте ещё раз.")
    finally:
        await processing_msg.delete()

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("about", cmd_about))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_text))

    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
