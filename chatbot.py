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

# Initialize the MongoDB database
def init_db():
    if items_col.count_documents({}) == 0:
        items_col.insert_many(ITEMS)
        logger.info("Items successfully inserted into the database.")
    else:
        logger.info("Items already present in the database.")

# Handlers
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Welcome to Cannabliss Ordering App! Use /order to place an order.')

def order(update: Update, context: CallbackContext) -> None:
    available_items = list(items_col.find({"grams_available": {"$gt": 0}}))

    logger.info(f"Available items: {available_items}")

    if not available_items:
        update.message.reply_text('Sorry, we are all smoked out of this Strain.')
        return

    keyboard = [[InlineKeyboardButton(f"{item['name']} - €{item['price']} (Qty: {item['grams_available']}g)", callback_data=item['name'])] for item in available_items]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Please choose your Strain:', reply_markup=reply_markup)

def item_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    context.user_data['item'] = query.data

    query.edit_message_text(text=f"You selected {query.data}. Please enter the quantity in grams you want to buy:")
    context.user_data['state'] = 'awaiting_quantity'

def handle_quantity(update: Update, context: CallbackContext) -> None:
    if context.user_data.get('state') == 'awaiting_quantity':
        try:
            quantity = int(update.message.text)
            item = items_col.find_one({"name": context.user_data['item']})
            if quantity <= 0 or quantity > item['grams_available']:
                update.message.reply_text(f"Invalid quantity. Please enter a value between 1 and {item['grams_available']}:")
                return

            context.user_data['quantity'] = quantity

            days_keyboard = [[InlineKeyboardButton(day, callback_data=day)] for day in TIME_SLOTS.keys()]
            reply_markup = InlineKeyboardMarkup(days_keyboard)
            update.message.reply_text(f"Please choose a pickup day:", reply_markup=reply_markup)
            context.user_data['state'] = 'awaiting_day'
        except ValueError:
            update.message.reply_text("Please enter a valid number.")

def day_callback(update: Update, context: CallbackContext) -> None:
    if context.user_data.get('state') == 'awaiting_day':
        query = update.callback_query
        query.answer()
        context.user_data['day'] = query.data

        times_keyboard = [[InlineKeyboardButton(time, callback_data=time)] for time in TIME_SLOTS[query.data]]
        reply_markup = InlineKeyboardMarkup(times_keyboard)
        query.edit_message_text(text=f"You selected {query.data}. Please choose a pickup time:", reply_markup=reply_markup)
        context.user_data['state'] = 'awaiting_time'

def time_callback(update: Update, context: CallbackContext) -> None:
    if context.user_data.get('state') == 'awaiting_time':
        query = update.callback_query
        query.answer()
        context.user_data['time'] = query.data

        item = items_col.find_one({"name": context.user_data['item']})

        # Decrement the inventory count
        items_col.update_one({"name": context.user_data['item']}, {"$inc": {"grams_available": -context.user_data['quantity']}})

        # Calculate total price
        total_price = context.user_data['quantity'] * item['price']

        # Insert the order into the orders collection
        orders_col.insert_one({
            "user_id": query.from_user.id,
            "username": query.from_user.username,
            "item_name": item['name'],
            "item_price": item['price'],
            "quantity": context.user_data['quantity'],
            "time_slot": context.user_data['time'],
            "pickup_date": context.user_data['day'],
            "total_price": total_price,
            "timestamp": datetime.now()
        })

        # Confirmation message to user
        query.edit_message_text(text=f"Order confirmed: {context.user_data['quantity']}g of {context.user_data['item']} at {context.user_data['time']} on {context.user_data['day']}. Total Price: €{total_price}. Thank you, {query.from_user.username}!")

        # Send confirmation message to admin
        context.bot.send_message(
            chat_id=6732532260,  # Make sure this variable is the admin's user ID or username
            text=f"New order placed by @{query.from_user.username} for {context.user_data['quantity']}g of {context.user_data['item']} scheduled for pickup at {context.user_data['time']} on {context.user_data['day']}. Total Price: €{total_price}."
        )

        context.user_data['state'] = None

def inventory(update: Update, context: CallbackContext) -> None:
    inventory_items = list(items_col.find())

    inventory_message = "Current Inventory:\n"
    for item in inventory_items:
        inventory_message += f"{item['name']} - €{item['price']} (Qty: {item['grams_available']}g)\n"

    update.message.reply_text(inventory_message)

def order_history(update: Update, context: CallbackContext) -> None:
    user_orders = list(orders_col.find({"user_id": update.message.from_user.id}))

    if not user_orders:
        update.message.reply_text('You have no order history.')
        return

    history_message = "Your Order History:\n"
    for order in user_orders:
        history_message += f"Item: {order['item_name']}, Price: €{order['item_price']}, Quantity: {order['quantity']}g, Time Slot: {order['time_slot']}, Date: {order['pickup_date']}\n"

    update.message.reply_text(history_message)

def add_item(update: Update, context: CallbackContext) -> None:
    try:
        args = context.args
        if len(args) != 3:
            update.message.reply_text('Usage: /additem <item_name> <price> <grams_available>')
            return

        item_name, price, grams_available = args
        price = int(price)
        grams_available = int(grams_available)

        items_col.insert_one({"name": item_name, "price": price, "grams_available": grams_available})
        update.message.reply_text(f'Item added: {item_name} - €{price} (Qty: {grams_available}g)')
    except Exception as e:
        update.message.reply_text(f'Error: {e}')

def update_item(update: Update, context: CallbackContext) -> None:
    try:
        args = context.args
        if len(args) != 3:
            update.message.reply_text('Usage: /updateitem <item_name> <price> <grams_available>')
            return

        item_name, price, grams_available = args
        price = int(price)
        grams_available = int(grams_available)

        items_col.update_one({"name": item_name}, {"$set": {"price": price, "grams_available": grams_available}})
        update.message.reply_text(f'Item updated: {item_name} - €{price} (Qty: {grams_available}g)')
    except Exception as e:
        update.message.reply_text(f'Error: {e}')

def delete_item(update: Update, context: CallbackContext) -> None:
    try:
        args = context.args
        if len(args) != 1:
            update.message.reply_text('Usage: /deleteitem <item_name>')
            return

        item_name = args[0]

        items_col.delete_one({"name": item_name})
        update.message.reply_text(f'Item deleted: {item_name}')
    except Exception as e:
        update.message.reply_text(f'Error: {e}')

# Main function
def main() -> None:
    init_db()

    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('order', order))
    dispatcher.add_handler(CallbackQueryHandler(item_callback, pattern='^(Pinkrunts|Fat Banana|Critical)$'))
    dispatcher.add_handler(CallbackQueryHandler(day_callback, pattern='^(Monday|Tuesday|Thursday|Friday)$'))
    dispatcher.add_handler(CallbackQueryHandler(time_callback, pattern='^(6:00 PM - 6:30 PM|6:30 PM - 7:00 PM|7:00 PM - 7:30 PM|7:30 PM - 8:00 PM|8:00 PM - 8:30 PM|8:30 PM - 9:00 PM|10:00 AM - 10:30 AM|10:30 AM - 11:00 AM|03:00 PM - 03:30 PM|03:30 PM - 04:00 PM|04:30 PM - 05:00 PM|05:00 PM - 05:30 PM|05:30 PM - 06:00 PM)$'))
    dispatcher.add_handler(CommandHandler('inventory', inventory))
    dispatcher.add_handler(CommandHandler('history', order_history))
    dispatcher.add_handler(CommandHandler('additem', add_item, pass_args=True))
    dispatcher.add_handler(CommandHandler('updateitem', update_item, pass_args=True))
    dispatcher.add_handler(CommandHandler('deleteitem', delete_item, pass_args=True))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_quantity))

    updater.start_polling()
    logger.info("Bot started polling.")
    updater.idle()

if __name__ == '__main__':
    main()
