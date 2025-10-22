# Disgram

A Python-based tool to forward messages from public Telegram channels to Discord using webhooks embeds. Disgram scrapes Telegram's public preview pages and forwards messages, including text, images, and formatted content, to Discord channels through webhooks.

## Workflow
The app starts a small Flask service (health and logs endpoints) and spawns one worker process per configured Telegram channel. Each worker scrapes Telegram preview pages and forwards content to Discord via webhooks. If a Discord thread ID is configured, messages go to that thread; otherwise they go to the channel via the webhook. A background monitor restarts crashed workers and recovers from stale states.

## Features

- No Telegram or Discord Bots required
- Forward messages from multiple Telegram channels to Discord
- Automated message source crediting in embeds
- Preserve message formatting (bold, italic, links, code blocks, etc.)
- Support for text and media content
- Automatic handling of missing messages
- Robust error handling and retry mechanisms
- Send messages to Discord threads using `DISCORD_THREAD_ID`
- **Advanced Rate Limiting**: Full Discord API compliance with bucket-based rate limiting
- **Comprehensive Media Handling**: Support for images, videos, and grouped media collections
- **Smart Grouped Media Processing**: Automatically detects and handles grouped media messages
- **Embed Formatting**: Rich Discord embeds with author avatars, names, and proper formatting
- **Health Monitoring**: Real-time health status at `/health` endpoint with rate limit tracking
- **Log Viewing**: View application logs via `/logs` endpoint for debugging
- **Process Management**: Automatic process spawning for multiple channels

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

- Copy `.env.example` to `.env` and fill in the required environment variables:
    ```
    cp .env.example .env
    ```
  - `DISCORD_WEBHOOK_URL`: Your Discord webhook URL.
  - `DISCORD_THREAD_ID` (Optional): The ID of the Discord thread to send messages to.
  - `TELEGRAM_CHANNELS`: Comma-separated list of public Telegram channel URLs.
  - `EMBED_COLOR`: Hex color code for embeds (e.g., 89a7d9 or 0x89a7d9).

- (Optional) Modify `config.py` for advanced settings:
  - `COOLDOWN`: Interval between checks (Suggested 300s or more to avoid IP bans).
  - `ERROR_PLACEHOLDER`: Message shown for unparseable content.

> [!TIP]
> **Starting from specific messages**: Instead of simply providing channel links in `TELEGRAM_CHANNELS`, you can provide specific message links in it to start forwarding from particular points.

## Usage

Local development (Flask development server):

```
python main.py
```

Production (Gunicorn):

```
bash start.sh
```

Alternatively:

```
gunicorn -w 1 -b 0.0.0.0:8000 main:app
```

Notes:
- Use a single Gunicorn worker to avoid duplicating the Telegram scraping subprocesses.
- The service binds to the `PORT` environment variable if provided, otherwise `8000`.

Windows (PowerShell) notes:
- Use the local development flow with PowerShell:

```
python .\main.py
```

The `start.sh` script is intended for general Linux environments and containers.

## Logging

The bot maintains logs at `/logs` endpoint that lets you view `Disgram.log` with the following information:
- Error messages
- New message notifications
- Operational status updates

## Rate Limiting

Disgram uses comprehensive Discord API rate limiting logic:

- **Per-Route Rate Limiting**: Tracks individual webhook endpoint limits
- **Global Rate Limiting**: Respects Discord's global rate limits (50 requests/second)
- **Bucket-Based Tracking**: Uses Discord's rate limit bucket system
- **429 Response Handling**: Automatic retry with proper wait times
- **Exponential Backoff**: Smart retry logic for network errors
- **Rate Limit Headers**: Parses and respects Discord's rate limit headers

## Health Monitoring

The bot includes a health check endpoint at `/health` for monitoring:
- **URL**: `http://localhost:5000/health` (or your server's address)
- **Method**: GET
- **Returns**: JSON with health status including rate limit information
- **Status Codes**: 
  - `200` - All systems healthy
  - `500` - Issues detected (check logs for details)

## Log Viewing

Access application logs via the `/logs` endpoint:
- **URL**: `http://localhost:5000/logs` (or your server's address)
- **Method**: GET
- **Returns**: Recent log entries from `Disgram.log`
- **Features**: Real-time log viewing for debugging and monitoring

## Log Management

Clear the contents of `Disgram.log` while preserving the latest message links via the `/logs/clear` endpoint:
- **URL**: `http://localhost:5000/logs/clear` (or your server's address)
- **Method**: POST
- **Returns**: JSON response with status, number of preserved channel links, and the latest message URLs
- **Features**: 
  - Removes all timestamped log entries
  - Preserves the header line
  - Extracts and preserves the **latest** message link for each channel (not the initial starting points)
  - Useful for managing log file size while maintaining progress

**Example:**
```bash
curl -X POST http://localhost:5000/logs/clear
```

**Response:**
```json
{
  "status": "success",
  "message": "Disgram.log cleared successfully",
  "preserved_links": 9,
  "latest_messages": [
    "https://t.me/Galaxy_leak/3649",
    "https://t.me/Seele_WW_Leak/3728",
    "..."
  ]
}
```

## Notes

- **Rate Limiting**: Discord rate limits are handled automatically with intelligent retry logic but be mindful of Telegram Preview Page's rates as well, in order to avoid IP bans.
- **Message Source**: Messages are fetched from Telegram's public preview page (https://t.me/s/{channel})
- **Channel Requirements**: Only works with public Telegram channels with accessible preview pages
- **Media Processing**: Supports single images, videos, and grouped media collections automatically
- **Thread vs Channel**: The bot automatically chooses between `webhook.py` (channel) and `threadhook.py` (thread) based on `DISCORD_THREAD_ID` configuration
- **Process Management**: Each Telegram channel runs in a separate process for better performance and isolation

## Known Issues
- Image quality of compressed images is too low to scrap from preview page. Use Telegram app for higher quality.
- Video URL extraction depends on video size, which determines if the Telegram public preview page will preview the video or not. If the video is too large, it won't be previewed and thus can't be scraped.
- The bot can not fully parse messages reliably with following content for now:
  - Uncompressed Media
  - Documents
  - Messages with replies

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.