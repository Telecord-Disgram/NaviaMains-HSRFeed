import random

# Add channels' links under quotes in the following format. 
Channels = [
    "https://t.me/randomchannel",
    "https://t.me/anotherchannel",
    "https://t.me/yetanotherchannel"
]
COOLDOWN = 300 # Strongly recommended to keep more than 5-20s in the long run to avoid being IP banned by Telegram. 
EMBED_COLOR = int(f"0x{random.randint(0, 0xFFFFFF):06x}", 16) # Change if you wish to.