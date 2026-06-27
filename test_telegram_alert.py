import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

from utils.telegram import send_telegram_messages, TelegramDeliveryError, telegram_config_status

def test_alerts():
    categories = ["Others", "Intraday", "Swing", "Premarket"]
    print("Testing Telegram configuration status:")
    for cat in categories:
        status = telegram_config_status(cat)
        print(f"Category: {cat} -> Status: {status}")

    print("\n--- Sending Test Messages ---")
    for cat in categories:
        print(f"\nSending message for category: {cat}...")
        try:
            res = send_telegram_messages(
                category=cat, 
                message=f"Test Telegram alert for category: {cat} from Antigravity Coding Assistant"
            )
            print(f"Success! Response: {res}")
        except TelegramDeliveryError as e:
            print(f"Delivery Error: {e}")
        except Exception as e:
            print(f"Unexpected Error: {e}")

if __name__ == "__main__":
    test_alerts()
