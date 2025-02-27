# Disgram

A Python-based tool to forward messages from public Telegram channels to Discord using webhooks embeds. Disgram scrapes Telegram's public preview pages and forwards messages, including text, images, and formatted content, to Discord channels through webhooks.

## Features

- No Telegram or Discord Bots required
- Forward messages from multiple Telegram channels to Discord
- Automated message source crediting in embeds
- Preserve message formatting (bold, italic, links, code blocks, etc.)
- Support for images and text content
- Automatic handling of missing messages
- Robust error handling and retry mechanisms
- Rate limit compliance for both Telegram and Discord
- Detailed logging system

## Prerequisites

- Python 3.6 or higher
- Discord Webhook URL
- Public Telegram Channel links

## Installation

1. Clone the repository:
```
git clone https://github.com/SimpNick6703/Disgram.git
cd Disgram
```

2. Install the required dependencies:
```
pip install -r requirements.txt
```

## Configuration

1. Open `config.py` and modify the following:
   - Add your Telegram channel links to the `Channels` list
   - Set your Discord webhook URL in `WEBHOOK_URL`
   - Adjust `COOLDOWN` if needed (default: 300 seconds)
   - Customize `EMBED_COLOR` if desired

2. (Optional) Initialize `Disgram.log` with specific message IDs to start forwarding from particular points

## Usage

1. Start the bot:
```
python main.py
```
2. The bot will create separate processes for each channel and begin forwarding messages.

3. To stop the bot, press `Ctrl + C`.

## Logging

The bot maintains logs in `Disgram.log` with the following information:
- Error messages
- New message notifications
- Operational status updates

## Notes

- Respect Telegram's rate limits by keeping appropriate cooldown times to avoid IP bans from Telegram
- The bot only works with public Telegram channels
- Messages are fetched from Telegram's public preview page (https://t.me/s/{channel})
- Discord webhook rate limits are handled automatically
- Image quality of compressed images is too low to scrap from preview page. Use Telegram app for higher quality.
- The bot can not parse messages with following content for now:
  - Uncompressed Images
  - Videos
  - Documents
  - Grouped Items
  - Messages with quoted text or replies

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details
