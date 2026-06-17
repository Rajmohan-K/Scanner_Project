import requests, os


api_config = {
    "Swing_Stocks": {
        'bot_token': '7874883850:AAEtYVn-FaoVhuQOiUiEiaS7k_o7gRK20N4',
        'chat_ids': ['7132113059']
    },
    "Premarket": {
        'bot_token': '7519620856:AAE_zBtJ5oX5nEO4kPIXjMYPoLHjgdOnZq0',
        'chat_ids': ['7132113059']
    },
    "Others": {
        'bot_token': '7605405036:AAEZGCAHlEJ5VmNuPLE5TW38965GzKkAUUs',
        'chat_ids': ['7132113059']
    },
    "Intraday_Stocks": {
        'bot_token': '7839730308:AAGUkaryseLw1N4fMBzHE-FuqqcVjW1eyrk',
        'chat_ids': ['7132113059']
    }
}




def send_telegram_messages(category, message, file_path=None):
    """Send text message or file with caption via Telegram."""

    aliases = {
        "Intraday": "Intraday_Stocks",
        "Swing": "Swing_Stocks",
        "Watchlist": "Others",
        "Stock Scanner": "Others",
    }
    category = aliases.get(category, category)
    if category not in api_config:
        category = "Others"

    bot_token = api_config[category]['bot_token']
    chat_ids = api_config[category]['chat_ids']

    message_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    document_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    for chat_id in chat_ids:
        try:
            # If file exists, send file with message as caption
            if file_path and os.path.isfile(file_path):

                with open(file_path, "rb") as file:
                    response = requests.post(
                        document_url,
                        data={
                            "chat_id": chat_id,
                            "caption": message
                        },
                        files={
                            "document": file
                        }
                    )

            # Otherwise send only text
            else:
                response = requests.post(
                    message_url,
                    data={
                        "chat_id": chat_id,
                        "text": message
                    }
                )

            if response.status_code == 200:
                print(f"Message sent successfully to {chat_id}")
            else:
                print(
                    f"Failed to send to {chat_id}: "
                    f"{response.status_code} - {response.text}"
                )

        except Exception as e:
            print(f"Error sending to {chat_id}: {e}")


# send_telegram_messages("Intraday","test")

# import requests

# BOT_TOKEN = "7874883850:AAEtYVn-FaoVhuQOiUiEiaS7k_o7gRK20N4"
# CHAT_ID = "7132113059"

# message = "Hello from Python!"

# url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# payload = {
#     "chat_id": CHAT_ID,
#     "text": message
# }

# response = requests.post(url, data=payload)

# print(response.json())