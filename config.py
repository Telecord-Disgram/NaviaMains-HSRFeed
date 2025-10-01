import os
import random
import dotenv

dotenv.load_dotenv()

Channels = os.getenv("TELEGRAM_CHANNELS").split(",")
COOLDOWN = 300 # Strongly recommended to keep more than 5-20s in the long run to avoid being IP banned by Telegram. 
EMBED_COLOR = os.getenv("EMBED_COLOR") if os.getenv("EMBED_COLOR") else int(f"0x{random.randint(0, 0xFFFFFF):06x}", 16) # int(f"0x89a7d9", 16)
ERROR_PLACEHOLDER = f"Unable to parse this message. Try heading to the message link leading to preview page or Telegram." # Placeholder for unparseable messages 
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL") # Replace this with your Discord webhook, webhookID and webhookToken are 19 and 68 characters long respectively.
THREAD_ID = os.getenv("DISCORD_THREAD_ID") if os.getenv("DISCORD_THREAD_ID") else None