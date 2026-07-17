import os
import asyncio
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import dotenv

dotenv.load_dotenv()

_client = None
_client_lock = asyncio.Lock()

async def _get_client() -> TelegramClient:
    """Get or initialize the Telethon client singleton."""
    global _client
    
    if _client is not None and _client.is_connected():
        return _client
        
    async with _client_lock:
        if _client is not None and _client.is_connected():
            return _client
            
        api_id = os.getenv("TG_API_ID")
        api_hash = os.getenv("TG_API_HASH")
        session_string = os.getenv("TG_SESSION_STRING")
        
        if not api_id or not api_hash or not session_string:
            raise ValueError("Telethon credentials not configured in .env")
            
        # Initialize client
        _client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        await _client.connect()
        
        if not await _client.is_user_authorized():
            raise Exception("Telethon session is invalid or expired.")
            
        return _client

async def _async_get_telethon_media(channel: str, message_ids: list[int]):
    """Async implementation to fetch media."""
    client = await _get_client()
    
    try:
        # Fetch the messages
        messages = await client.get_messages(channel, ids=message_ids)
        
        if not messages:
            return []
            
        # Ensure it's a list (get_messages returns a single object if given a single ID)
        if not isinstance(messages, list):
            messages = [messages]
            
        downloaded_items = []
        
        for msg in messages:
            if not msg or not msg.media:
                continue
                
            is_spoiler = getattr(msg.media, 'spoiler', False)
            
            # Use telethon to download the file into memory
            import tempfile
            temp_dir = tempfile.gettempdir()
            
            import uuid
            unique_id = uuid.uuid4().hex[:8]
            target_path = os.path.join(temp_dir, f"telethon_dl_{unique_id}")
            
            # This might take some time for large videos
            file_path = await client.download_media(msg.media, file=target_path)
            
            if not file_path:
                continue
                
            file_size = os.path.getsize(file_path)
            
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
                
            # Clean up the temp file
            try:
                os.remove(file_path)
            except OSError:
                pass
                
            is_too_large = file_size > (10 * 1024 * 1024)
            
            item_type = 'document'
            if hasattr(msg.media, 'photo'):
                item_type = 'image'
            elif hasattr(msg.media, 'document'):
                # Check mime type to see if it's a video
                if any(attr.mime_type.startswith('video/') for attr in msg.media.document.attributes if hasattr(attr, 'mime_type')):
                    item_type = 'video'
                else:
                    item_type = 'document'
                    
            # Determine filename
            filename = f"media_{unique_id}.bin"
            if file_path:
                filename = os.path.basename(file_path)
                
            downloaded_items.append({
                'type': 'video_too_large' if (item_type == 'video' and is_too_large) else item_type,
                'data': None if is_too_large else file_bytes,
                'filename': filename,
                'is_spoiler': is_spoiler,
                'is_too_large': is_too_large,
                'size': file_size
            })
            
        return downloaded_items
        
    except Exception as e:
        print(f"Error fetching media via Telethon for {channel}/{message_ids}: {e}")
        return []

def get_telethon_media(channel: str, message_ids: list[int]):
    """
    Synchronous wrapper to fetch media via Telethon.
    Used by webhook.py which is currently synchronous.
    """
    return asyncio.run(_async_get_telethon_media(channel, message_ids))

async def _async_check_health() -> bool:
    try:
        client = await _get_client()
        return await client.is_user_authorized()
    except Exception:
        return False

def check_telethon_health() -> bool:
    """
    Synchronous wrapper to check if Telethon session is alive.
    Used by main.py health endpoint.
    """
    if not os.getenv("TG_SESSION_STRING"):
        return False
    return asyncio.run(_async_check_health())
