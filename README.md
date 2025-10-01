# Disgram

A Python-based tool to forward messages from public Telegram channels to Discord using webhooks embeds. Disgram scrapes Telegram's public preview pages and forwards messages, including text, images, and formatted content, to Discord channels through webhooks.

## Workflow
```mermaid
flowchart TD
    A[Start: python main.py] --> B[Load config.py]
    B --> C[Initialize Logging]
    C --> D{Thread ID Exists?}
    D --> |Yes| E[Launch threadhook.py]
    D --> |No| F[Launch webhook.py]
    
    %% threadhook.py workflow
    E --> G1[URL: webhook?thread_ID]
    G1 --> H1[Read Log for Last Message]
    H1 --> I1[Start Main Loop]

    %% webhook.py workflow
    F --> G2[URL: webhook]
    G2 --> H2[Read Log for Last Message]
    H2 --> I2[Start Main Loop]
    
    %% Common workflow for both scripts
    I1 --> J[Scrape Telegram Prev Page]
    I2 --> J
    J --> K{New Message Found?}
    K --> |No| L[Wait and Retry]
    L --> J
    K --> |Yes| M[Parse and Extract Content]
    M --> N[Text Content]
    M --> O[Media Content] 
    M --> P[Grouped Media]
    N --> Q[Format Text for Discord]
    O --> Q
    P --> Q
    Q --> R[Create Discord Embed]
    R --> S[Add Source Credits]
    S --> T[Send Message]
    T --> |threadhook.py| U[Send to Thread]
    T --> |webhook.py| V[Send to Channel]
    U --> W{Send Successful?}
    V --> W
    W --> |No| X[Error & Retry Logic]
    X --> Y[Log Error to Disgram.log]
    Y --> Z{Retry Available?}
    Z --> |Yes| AA[Wait and Retry]
    AA --> T
    Z --> |No| AB[Skip Message]
    W --> |Yes| AC[Update Disgram.log]
    AC --> AD[Continue to Next Message]
    AB --> AD
    AD --> AE[Wait for Cooldown]
    AE --> J

    %% Error Logging
    AF[Error Logging] -.-> Y
    AF -.-> AC
    AF -.-> AD

    %% Rate Limit Handling
    AG[Rate Limit Handling] -.-> U
    AG -.-> J
    AG -.-> V

    %% Shutdown
    AH[Shutdown: Ctrl + C] --> AI[Terminate All Processes]
    AI --> AJ[Wait for Termination]
    AJ --> AK[Exit Program]

    classDef startEnd fill:#2E8B57,stroke:#000,stroke-width:3px,color:#fff
    classDef process fill:#4169E1,stroke:#000,stroke-width:2px,color:#fff
    classDef decision fill:#FF6B35,stroke:#000,stroke-width:3px,color:#fff
    classDef error fill:#DC143C,stroke:#000,stroke-width:3px,color:#fff
    classDef support fill:#FFD700,stroke:#000,stroke-width:2px,color:#000
    classDef thread fill:#9370DB,stroke:#000,stroke-width:2px,color:#fff
    classDef channel fill:#20B2AA,stroke:#000,stroke-width:2px,color:#fff
    
    class A,AK startEnd
    class B,C,G1,G2,H1,H2,I1,I2,J,L,M,N,O,P,Q,R,S,T,AC,AD,AE process
    class D,K,W,Z decision
    class X,Y,AA,AB,AI,AJ error
    class AF,AG,AH support
    class E,U thread
    class F,V channel
```

## Features

- No Telegram or Discord Bots required
- Forward messages from multiple Telegram channels to Discord
- Automated message source crediting in embeds
- Preserve message formatting (bold, italic, links, code blocks, etc.)
- Support for text and media content
- Support for text and media content
- Automatic handling of missing messages
- Robust error handling and retry mechanisms
- Rate limit compliance for both Telegram and Discord
- Detailed logging system and health monitoring endpoint (`/health`)

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

- Open `config.py` and modify the following:
  - Adjust `COOLDOWN` if needed (Suggested 300s or more).
  - Customize `EMBED_COLOR` and `ERROR_PLACEHOLDER` if desired.

> [!TIP]
> To send messages to a Thread under the channel of the webhook, replace `THREAD_ID = None` as `THREAD_ID = {thread_id}` in `config.py`.
>
> (Optional but recommended) Initialize `Disgram.log` with specific message IDs to start forwarding from particular message link.

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

## Health Monitoring

The bot includes a health check endpoint at `/health` for monitoring:
- **URL**: `http://localhost:5000/health` (or your server's address)
- **Method**: GET
- **Returns**: JSON with health status
- **Status Codes**: 
  - `200` - All systems healthy
  - `500` - Issues detected (check logs for details)

## Notes

- Respect Telegram's rate limits by keeping appropriate cooldown times to avoid IP bans from Telegram
- Messages are fetched from Telegram's public preview page (https://t.me/s/{channel})
- The bot only works with public Telegram channels with an accessible preview page.
- Discord webhook rate limits are handled automatically.

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