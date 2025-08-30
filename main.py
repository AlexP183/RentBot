import os
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)

from sqlalchemy import create_engine, Column, Integer, String, DateTime, desc
from sqlalchemy.orm import sessionmaker, declarative_base

# ---------- Конфиг ----------
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Samara")
PRICE_FILE_PATH = os.getenv("PRICE_FILE_PATH", "files/price.pdf")
CONTRACT_FILE_PATH = os.getenv("CONTRACT_FILE_PATH", "files/contract.pdf")
PRICE_URL = os.getenv("PRICE_URL")
CONTRACT_URL = os.getenv("CONTRACT_URL")

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в .env")

tz = ZoneInfo(TIMEZONE)

# ---------- БД ----------
Base = declarative_base()
engine = create_engine("sqlite:///bot.db")
SessionLocal = sessionmaker(bind=engine)


class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    chat_id = Column(Integer, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    note = Column(String, default="Возврат инструмента")


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    user_name = Column(String, default="")
    text = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(engine)

# ---------- Стейты ----------
ASK_DATETIME, ASK_NOTE, ASK_REVIEW_TEXT = range(3)


# ---------- Утилиты ----------
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Прайс", callback_data="show_price"),
         InlineKeyboardButton("�� Договор", callback_data="show_contract")],
        [InlineKeyboardButton("📞 Наши контакты", callback_data="show_contacts")],
        [InlineKeyboardButton("⏰ Установить напоминание", callback_data="set_reminder")],
        [InlineKeyboardButton("💬 Отзывы", callback_data="reviews")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ])


# ---------- Хендлеры ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛠️ Добро пожаловать в сервис аренды инструмента!\n\n"
        "Здесь вы можете:\n"
        "• �� Посмотреть прайс\n"
        "• 📝 Ознакомиться с договором\n"
        "• �� Связаться с нами\n"
        "• ⏰ Установить напоминание о возврате\n"
        "• �� Читать и оставлять отзывы\n\n"
        "Выберите нужное действие:"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=main_menu_keyboard())
    else:
        await update.callback_query.message.reply_text(text, reply_markup=main_menu_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "📋 Доступные команды:\n\n"
        "/start — главное меню\n"
        "/menu — главное меню\n"
        "/price — прайс\n"
        "/contract — договор\n"
        "/contacts — контакты\n"
        "/reminder — установить напоминание\n"
        "/reviews — отзывы\n\n"
        "⏰ Напоминание: отправьте дату и время в формате «ДД.ММ.ГГГГ ЧЧ:ММ»\n"
        "Например: 30.08.2025 18:30"
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception: %s", context.error)


async def send_document_by_path_or_url(update_obj, context, path, url, caption):
    chat_id = update_obj.effective_chat.id
    if url:
        await context.bot.send_message(chat_id, f"{caption}\n{url}")
        return
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            await context.bot.send_document(chat_id, document=InputFile(f, filename=os.path.basename(path)),
                                            caption=caption)
    else:
        await context.bot.send_message(chat_id, "Файл недоступен. Задайте URL или положите файл в указанный путь.")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data

    if data == "show_price":
        await q.answer()
        await send_document_by_path_or_url(update, context, PRICE_FILE_PATH, PRICE_URL, "📄 Актуальный прайс:")

    elif data == "show_contract":
        await q.answer()
        await send_document_by_path_or_url(update, context, CONTRACT_FILE_PATH, CONTRACT_URL, "�� Договор аренды:")

    elif data == "show_contacts":
        await q.answer()
        # Кликабельный номер и адрес с навигацией
        phone_number = "+79536353102"
        address = "г.Маркс, ул. 2-я Сосновая, д. 12"
        address_url = "https://maps.google.com/?q=г.Маркс, ул. 2-я Сосновая, д. 12"

        contacts_text = (
            "�� Наши контакты:\n\n"
            f"📱 Телефон: [{phone_number}](tel:{phone_number})\n"
            f"📧 WhatsApp: [Написать в WhatsApp](https://wa.me/79536353102)\n\n"
            "🕒 Время работы:\n"
            "Пн-Пт: 8:00 - 18:00\n"
            "Сб: 9:00 - 16:00\n"
            "Вс: выходной\n\n"
            f"📍 Адрес: [{address}]({address_url})\n\n"
            "�� Как добраться: нажмите на адрес для открытия в навигаторе"
        )
        await q.message.reply_text(
            contacts_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

    elif data == "set_reminder":
        await q.answer()
        await q.message.reply_text(
            "⏰ Установка напоминания о возврате инструмента\n\n"
            "Отправьте дату и время возврата в формате:\n"
            "ДД.ММ.ГГГГ ЧЧ:ММ\n\n"
            "Например: 30.08.2025 18:30\n\n"
            "Или отправьте «-» для отмены."
        )
        return ASK_DATETIME

    elif data == "reviews":
        await q.answer()
        await show_reviews(update, context)

    elif data == "help":
        await help_cmd(update, context)


# ---------- Напоминания ----------
def parse_datetime_local(s: str) -> datetime | None:
    s = " ".join(s.split())
    try:
        dt_local = datetime.strptime(s, "%d.%m.%Y %H:%M")
        return dt_local.replace(tzinfo=tz)
    except Exception:
        return None


async def ask_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "-":
        await update.message.reply_text("❌ Установка напоминания отменена.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    dt_local = parse_datetime_local(text)
    if not dt_local:
        await update.message.reply_text(
            "❌ Неверный формат даты и времени.\n\n"
            "Правильный формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Например: 30.08.2025 18:30\n\n"
            "Повторите ввод или отправьте «-» для отмены."
        )
        return ASK_DATETIME

    # Проверяем, что время в будущем
    now = datetime.now(tz)
    if dt_local <= now:
        await update.message.reply_text(
            "❌ Время напоминания должно быть в будущем.\n\n"
            "Повторите ввод или отправьте «-» для отмены."
        )
        return ASK_DATETIME

    # Спрашиваем заметку
    context.user_data["reminder_datetime"] = dt_local
    await update.message.reply_text(
        "✅ Время установлено!\n\n"
        "Добавьте заметку (например, «Перфоратор Bosch»)\n"
        "Или отправьте «-», чтобы пропустить:"
    )
    return ASK_NOTE


async def ask_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    if note == "-":
        note = "Возврат инструмента"

    dt_local = context.user_data.get("reminder_datetime")
    dt_utc = dt_local.astimezone(timezone.utc)

    with SessionLocal() as db:
        reminder = Reminder(
            user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            due_at=dt_utc,
            note=note,
        )
        db.add(reminder)
        db.commit()
        reminder_id = reminder.id

    logger.info(f"Создано напоминание ID {reminder_id} для пользователя {update.effective_user.id} на {dt_utc}")

    # Планируем напоминание
    context.job_queue.run_once(
        callback=notify_user,
        when=dt_utc,
        name=f"reminder_{reminder_id}",
        data={"user_id": update.effective_user.id, "chat_id": update.effective_chat.id, "note": note}
    )

    await update.message.reply_text(
        f"✅ Напоминание установлено!\n\n"
        f"⏰ Время: {dt_local.strftime('%d.%m.%Y %H:%M')} ({TIMEZONE})\n"
        f"📝 Заметка: {note}\n\n"
        f"Я Вас оповещу в личные сообщения.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END


async def notify_user(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data["chat_id"]
    note = data["note"]
    user_id = data["user_id"]

    logger.info(f"Отправляю напоминание пользователю {user_id} в чат {chat_id}: {note}")

    try:
        await context.bot.send_message(
            chat_id,
            f"⏰ Напоминание о возврате инструмента!\n\n"
            f"📝 {note}\n\n"
            f"Пора вернуть инструмент. Спасибо за использование нашего сервиса! 🛠️"
        )
        logger.info(f"Напоминание успешно отправлено пользователю {user_id}")
    except Exception as e:
        logger.exception(f"Ошибка отправки напоминания пользователю {user_id}: {e}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Операция отменена.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ---------- Отзывы ----------
async def show_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE, limit: int = 10):
    with SessionLocal() as db:
        items = db.query(Review).order_by(desc(Review.created_at)).limit(limit).all()

    if not items:
        await update.effective_message.reply_text(
            "�� Пока нет отзывов.\n\n"
            "Нажмите «✍️ Оставить отзыв», чтобы написать первый!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Оставить отзыв", callback_data="review_add")]])
        )
        return

    lines = []
    for r in items:
        name = r.user_name or "Без имени"
        dt_local = r.created_at.astimezone(tz)
        lines.append(f"💬 {r.text}\n  👤 {name}, {dt_local.strftime('%d.%m.%Y %H:%M')}")
    text = "�� Последние отзывы:\n\n" + "\n\n".join(lines)

    await update.effective_message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Оставить отзыв", callback_data="review_add")]])
    )


async def ask_review_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(
        "✍️ Напишите ваш отзыв одним сообщением.\n\n"
        "Расскажите о качестве инструмента, обслуживании, удобстве аренды.\n\n"
        "Для отмены отправьте /cancel"
    )
    return ASK_REVIEW_TEXT


async def ask_review_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("❌ Пустой отзыв не сохраняю. Напишите текст или /cancel.")
        return ASK_REVIEW_TEXT

    user = update.effective_user
    user_name = user.full_name or (user.username and f"@{user.username}") or "Без имени"

    with SessionLocal() as db:
        db.add(Review(
            user_id=user.id,
            user_name=user_name,
            text=text,
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()

    await update.message.reply_text(
        "✅ Спасибо! Ваш отзыв сохранён.\n\n"
        "Мы ценим ваше мнение и будем работать над улучшением сервиса! 🙏",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END


# ---------- Команды ----------
async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_document_by_path_or_url(update, context, PRICE_FILE_PATH, PRICE_URL, "�� Актуальный прайс:")


async def cmd_contract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_document_by_path_or_url(update, context, CONTRACT_FILE_PATH, CONTRACT_URL, "📝 Договор аренды:")


async def cmd_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_number = "+79536353102"
    address = "г.Маркс, ул. 2-я Сосновая, д. 12"
    address_url = "https://maps.google.com/?q=г.Маркс, ул. 2-я Сосновая, д. 12"

    contacts_text = (
        "�� Наши контакты:\n\n"
        f"📱 Телефон: [{phone_number}](tel:{phone_number})\n"
        f"📧 WhatsApp: [Написать в WhatsApp](https://wa.me/79536353102)\n\n"
        "🕒 Время работы:\n"
        "Пн-Пт: 8:00 - 18:00\n"
        "Сб: 9:00 - 16:00\n"
        "Вс: выходной\n\n"
        f"📍 Адрес: [{address}]({address_url})\n\n"
        "�� Как добраться: нажмите на адрес для открытия в навигаторе"
    )
    await update.message.reply_text(
        contacts_text,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )


async def cmd_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏰ Установка напоминания о возврате инструмента\n\n"
        "Отправьте дату и время возврата в формате:\n"
        "ДД.ММ.ГГГГ ЧЧ:ММ\n\n"
        "Например: 30.08.2025 18:30\n\n"
        "Или отправьте «-» для отмены."
    )
    return ASK_DATETIME


async def cmd_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_reviews(update, context)


# ---------- Main ----------
def build_application() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("contract", cmd_contract))
    app.add_handler(CommandHandler("contacts", cmd_contacts))
    app.add_handler(CommandHandler("reminder", cmd_reminder))
    app.add_handler(CommandHandler("reviews", cmd_reviews))

    app.add_handler(
        CallbackQueryHandler(on_button, pattern="^(show_price|show_contract|show_contacts|set_reminder|reviews)$"))
    app.add_handler(CallbackQueryHandler(ask_review_start, pattern="^review_add$"))

    conv_reminder = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(on_button, pattern="^set_reminder$"),
            CommandHandler("reminder", cmd_reminder)
        ],
        states={
            ASK_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_datetime)],
            ASK_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_note)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(conv_reminder)

    conv_reviews = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_review_start, pattern="^review_add$")],
        states={
            ASK_REVIEW_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_review_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(conv_reviews)

    return app


if __name__ == "__main__":
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)