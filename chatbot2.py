from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
import logging
from pymongo import MongoClient
from datetime import datetime

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
BOT_TOKEN = '6995824033:AAGWGYRaZQr_whbWJhZsMNOLqHwOeMFj_TE'

# MongoDB connection settings
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "shopBot"
ITEMS_COLLECTION = "Strains"
ORDERS_COLLECTION = "Grams"

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
items_col = db[ITEMS_COLLECTION]
orders_col = db[ORDERS_COLLECTION]

# Example items
ITEMS = [
    {"name": "Pinkrunts", "price": 8, "grams_available": 50},
]

# Pickup time slots with specific days
TIME_SLOTS = {
    "Monday": ["6:00 PM - 6:30 PM", "6:30 PM - 7:00 PM", "7:00 PM - 7:30 PM", "7:30 PM - 8:00 PM", "8:00 PM - 8:30 PM", "8:30 PM - 9:00 PM"],
    "Tuesday": ["10:00 AM - 10:30 AM", "10:30 AM - 11:00 AM"],
    "Thursday": ["10:00 AM - 10:30 AM", "10:30 AM - 11:00 AM"],
    "Friday": ["03:00 PM - 03:30 PM", "03:30 PM - 04:00 PM", "04:30 PM - 05:00 PM", "05:00 PM - 05:30 PM", "05:30 PM - 06:00 PM"]
}

# Group chat ID
GROUP_CHAT_ID = -2099666448

# Initialize the MongoDB database
def init_db():
    if items_col.count_documents({}) == 0:
        items_col.insert_many(ITEMS)
        logger.info("Items successfully inserted into the database.")
    else:
        logger.info("Items already present in the database.")

# Check if user is a member of the group chat
def is_group_member(user_id, context):
    try:
        member = context.bot.get_chat_member(GROUP_CHAT_ID, user_id)
        logger.info(f"Checked group membership for {user_id}: Status is {member.status}")
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Failed to check membership for user {user_id}: {e}")
        return False

# Handlers
def start(update: Update, context: CallbackContext) -> None:
    if is_group_member(update.message.from_user.id, context):
        update.message.reply_text('Welcome to Cannabliss Ordering App! Use /order to place an order.')
    else:
        update.message.reply_text('Access denied. You must be a member of the Cannabliss group to use this bot.')

def order(update: Update, context: CallbackContext) -> None:
    if not is_group_member(update.message.from_user.id, context):
        update.message.reply_text('Access denied. You must be a member of the Cannabliss group to use this bot.')
        return
    
    available_items = list(items_col.find({"grams_available": {"$gt": 0}}))
    if not available_items:
        update.message.reply_text('Currently, all strains are out of stock.')
        return

    keyboard = [[InlineKeyboardButton(f"{item['name']} - €{item['price']} (Available: {item['grams_available']}g)", callback_data=f"order_{item['name']}")] for item in available_items]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Select a strain to order:', reply_markup=reply_markup)

def handle_quantity(update: Update, context: CallbackContext) -> None:
    if context.user_data.get('state') == 'awaiting_quantity':
        message = update.message.text
        try:
            quantity = int(message)
            if quantity <= 0:
                update.message.reply_text("Quantity must be a positive number.")
                return
            item = items_col.find_one({"name": context.user_data['item']})
            if quantity > item['grams_available']:
                update.message.reply_text(f"Only {item['grams_available']} grams available, please enter a lesser quantity.")
                return

            context.user_data['quantity'] = quantity
            update.message.reply_text(f"Quantity set to {quantity} grams. Please proceed by selecting the pickup time.")

            days_keyboard = [[InlineKeyboardButton(day, callback_data=f"time_{day}") for day in TIME_SLOTS]]
            reply_markup = InlineKeyboardMarkup(days_keyboard)
            update.message.reply_text('Select a day for pickup:', reply_markup=reply_markup)
            context.user_data['state'] = 'awaiting_time'
        except ValueError:
            update.message.reply_text("Please enter a valid integer for quantity.")

# Add remaining necessary handlers and callback functions

# Main function to start the bot
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('order', order))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_quantity))
    # Add other handlers as needed

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
