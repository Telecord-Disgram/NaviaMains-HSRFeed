import time
import datetime
import requests
import sys
import re
import os
import io
from dateutil import parser
from bs4 import BeautifulSoup
import discord
from discord import SyncWebhook, Embed, File
from config import WEBHOOK_URL, THREAD_ID, COOLDOWN, EMBED_COLOR, ERROR_PLACEHOLDER

def log_message(message: str, log_type: str = "info") -> None:
    """Log messages to console and to Disgram.log for specific message types."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} {message}"
    print(log_entry)
    if log_type in ["error", "new_message", "status"]:
        with open("Disgram.log", "a", encoding="utf-8") as log_file:
            log_file.write(log_entry + "\n")

def is_message_logged(channel: str, number: int) -> bool:
    """Check if the given message number has already been logged for the channel."""
    try:
        with open("Disgram.log", "r", encoding="utf-8") as log_file:
            for line in log_file:
                match = re.search(rf"https://t.me/{channel}/(\d+)", line)
                if match and int(match.group(1)) >= number:
                    return True
    except FileNotFoundError:
        pass
    return False

def scrapeTelegramMessageBox(channel: str) -> list:
    """Scrape the latest messages from the Telegram channel preview page."""
    max_retries = 5
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            log_message(f"Scraping messages from Telegram channel: {channel} (Attempt {attempt + 1})")
            tg_html = requests.get(f'https://t.me/s/{channel}', timeout=10)
            tg_html.raise_for_status()
            tg_soup = BeautifulSoup(tg_html.text, 'html.parser')
            return tg_soup.find_all('div', {'class': 'tgme_widget_message_wrap js-widget_message_wrap'})
        except requests.exceptions.RequestException as e:
            log_message(f"Error scraping Telegram: {e}", log_type="error")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                log_message("Max retries reached. Skipping this iteration.", log_type="error")
                return []
    return []

def getAuthorIcon(tg_box) -> str | None:
    """Extract the author's profile icon URL."""
    icon_element = tg_box.find('i', {'class': 'tgme_widget_message_user_photo'})
    if icon_element:
        img_tag = icon_element.find('img')
        if img_tag and 'src' in img_tag.attrs:
            return img_tag['src']
    return None

def getAuthorName(tg_box) -> str | None:
    """Extract the author's name."""
    author_name = tg_box.find('a', {'class': 'tgme_widget_message_owner_name'})
    return author_name.text.strip() if author_name else None

def getLink(tg_box) -> str | None:
    """Extract the Telegram message link."""
    msg_link = tg_box.find_all('a', {'class': 'tgme_widget_message_date'}, href=True)
    return msg_link[0]['href'] if msg_link else None

def _render_children(element, in_quote=False) -> str:
    """Helper to render elements inside blockquotes and other tags recursively."""
    parts = []
    for child in element.children:
        parts.append(_render_node(child, in_quote))
    return ''.join(parts)

def _render_node(node, in_quote=False) -> str:
    """Helper to format individual HTML elements into Markdown."""
    if getattr(node, 'name', None) is None:
        return str(node)

    name = node.name
    if name == 'a':
        text = _render_children(node, in_quote)
        href = node.get('href', '')
        if text == href:
            return href
        return f"[{text}]({href})" if href else text
    if name == 'pre':
        content = node.get_text()
        return f"```{content}```"
    if name in ('b', 'strong'):
        return f"**{_render_children(node, in_quote)}**"
    if name == 'tg-spoiler':
        return f"||{_render_children(node, in_quote)}||"
    if name in ('i', 'em'):
        return f"*{_render_children(node, in_quote)}*"
    if name == 'u':
        return f"__{_render_children(node, in_quote)}__"
    if name in ('s', 'strike', 'del'):
        return f"~~{_render_children(node, in_quote)}~~"
    if name == 'br':
        return '\n'
    if name == 'blockquote':
        if in_quote:
            return _render_children(node, in_quote=True)
        inner = _render_children(node, in_quote=True)
        inner = inner.replace('\r\n', '\n').replace('\r', '\n')
        lines = inner.split('\n')
        quoted = "\n".join(["> " + l if l != "" else "> " for l in lines]) + "\n"
        return quoted

    return _render_children(node, in_quote)

def getText(tg_box) -> str | None:
    """Extract and format the message text."""
    msg_text = tg_box.find_all('div', {'class': 'tgme_widget_message_text js-message_text'})
    if not msg_text:
        return None
    return _render_children(msg_text[0])

def getTextFromIndividualMessage(msg_link: str) -> str | None:
    """Extract text from an individual message page (fallback for media groups)."""
    if not msg_link:
        return None
        
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            response = requests.get(msg_link, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            text_div = soup.find('div', class_='tgme_widget_message_text')
            if text_div:
                text_content = text_div.get_text(strip=True)
                if text_content:
                    return text_content
            
            og_desc = soup.find('meta', property='og:description')
            if og_desc:
                content_attr = og_desc.get('content')
                if content_attr:
                    content = str(content_attr).strip()
                    if content and _is_likely_message_content(content):
                        return content
            return None
        except Exception as e:
            log_message(f"Error fetching text from individual message {msg_link}: {e}", log_type="error")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return None
    return None

def _is_likely_message_content(content: str) -> bool:
    """Check to filter out obvious channel descriptions."""
    if not content:
        return False
    
    content_lower = content.lower().strip()
    channel_desc_patterns = [
        r'^the official .+ on telegram',
        r'official .+ channel',
        r'.+ official channel', 
        r'welcome to .+',
        r'much recursion\. very telegram\. wow\.',
        r'^.+\s+–\s+.+$',
    ]
    
    for pattern in channel_desc_patterns:
        if re.match(pattern, content_lower):
            return False
    
    if len(content.split()) <= 1:
        return False
    
    return True

def getImage(tg_box) -> str | None:
    """Get single message image URL."""
    msg_image = tg_box.find('a', {'class': 'tgme_widget_message_photo_wrap'}, href=True)
    if msg_image:
        startIndex = msg_image['style'].find("background-image:url('") + 22
        endIndex = msg_image['style'].find(".jpg')") + 4
        if startIndex > 21 and endIndex > 3:
            return msg_image['style'][startIndex:endIndex]
    return None

def getAllImages(tg_box) -> list[str]:
    """Get all image URLs for media groups."""
    images = []
    msg_images = tg_box.find_all('a', {'class': 'tgme_widget_message_photo_wrap'})
    for msg_image in msg_images:
        if msg_image.get('style'):
            style = msg_image['style']
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                start_pos = style.find("background-image:url('")
                end_pos = style.find(f"{ext}')")
                if start_pos > -1 and end_pos > -1:
                    start_index = start_pos + 22
                    end_index = end_pos + len(ext)
                    if start_index > 21 and end_index > start_index:
                        images.append(style[start_index:end_index])
                    break
    return images

def getVideo(tg_box) -> str | None:
    """Get single video URL."""
    video_element = tg_box.find('video', {'class': 'tgme_widget_message_video'})
    if video_element and 'src' in video_element.attrs:
        return video_element['src']
    return None

def getAllVideos(tg_box) -> list[str]:
    """Get all video URLs for media groups."""
    videos = []
    video_elements = tg_box.find_all('video', {'class': 'tgme_widget_message_video'})
    for video_element in video_elements:
        if video_element.get('src'):
            videos.append(video_element['src'])
    return videos

def getTimestamp(tg_box) -> datetime.datetime | None:
    """Extract message timestamp."""
    time_element = tg_box.find('time', {'datetime': True})
    if time_element and 'datetime' in time_element.attrs:
        return parser.isoparse(time_element['datetime'])
    return None

def download_file(url: str | None, prefix: str, ext_fallback: str, timeout: int = 10) -> tuple[io.BytesIO | None, str | None]:
    """Download a file from url and return a BytesIO object and filename."""
    if not url:
        return None, None
    max_retries = 3
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            
            content_bytes = response.content
            if not content_bytes:
                raise ValueError("Downloaded file content is empty (0 bytes)")
            
            ext = os.path.splitext(url)[1]
            if not ext or '?' in ext:
                ext = url.split('.')[-1].split('?')[0] if '.' in url else ext_fallback
            if not ext.startswith('.'):
                ext = f".{ext}"
            if len(ext) > 5:
                ext = f".{ext_fallback}"
                
            filename = f"{prefix}_{int(time.time())}_{attempt}{ext}"
            return io.BytesIO(content_bytes), filename
        except Exception as e:
            log_message(f"Error downloading {prefix}: {e}", log_type="error")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
    return None, None

def download_image(url: str | None) -> tuple[io.BytesIO | None, str | None]:
    """Download an image file."""
    return download_file(url, "img", "jpg", timeout=10)

def download_video(url: str | None) -> tuple[io.BytesIO | None, str | None]:
    """Download a video file."""
    return download_file(url, "video", "mp4", timeout=30)

def send_webhook_message(webhook_url: str, thread_id: str | None = None, **kwargs) -> tuple[bool, bool]:
    """Send webhook message via discord.py SyncWebhook with native error handling.
    Returns (success, is_payload_too_large)"""
    try:
        webhook = SyncWebhook.from_url(webhook_url)
        if thread_id:
            kwargs['thread'] = discord.Object(id=int(thread_id))
        webhook.send(**kwargs)
        return True, False
    except discord.HTTPException as e:
        log_message(f"Discord HTTP Exception: {e}", log_type="error")
        is_payload_too_large = (e.status == 413)
        return False, is_payload_too_large
    except Exception as e:
        log_message(f"Error sending message to Discord: {e}", log_type="error")
        return False, False

def sendMessage(msg_link: str, msg_text: str | None, msg_image: str | None, msg_video: str | None, 
                author_name: str, icon_url: str | None, timestamp: datetime.datetime | None = None, 
                all_images: list[str] | None = None, all_videos: list[str] | None = None) -> None:
    """Send a Telegram message to Discord webhook (with thread support)."""
    images_to_send = all_images if all_images else ([msg_image] if msg_image else [])
    videos_to_send = all_videos if all_videos else ([msg_video] if msg_video else [])
    
    if len(images_to_send) > 1 or len(videos_to_send) > 1:
        log_message(f"Sending grouped media message with {len(images_to_send)} images and {len(videos_to_send)} videos: {msg_link}", log_type="new_message")
        sendGroupedMediaMessage(msg_link, msg_text, images_to_send, videos_to_send, author_name, icon_url, timestamp)
        return
    
    image_data, image_filename = None, None
    if images_to_send:
        image_data, image_filename = download_image(images_to_send[0])
        
    video_data, video_filename = None, None
    video_sent_as_attachment = False
    if videos_to_send:
        try:
            video_data, video_filename = download_video(videos_to_send[0])
            if video_data and video_filename:
                video_sent_as_attachment = True
                log_message(f"Video will be sent as attachment: {videos_to_send[0]}", log_type="new_message")
        except Exception as e:
            log_message(f"Failed to download video, will fallback to link: {e}", log_type="error")
            
    try:
        embed = Embed(title='Message Link', url=msg_link, color=EMBED_COLOR, timestamp=timestamp)
        if msg_text:
            embed.description = msg_text
        embed.set_author(name=author_name, icon_url=icon_url, url=msg_link)
        
        files = []
        if image_data and image_filename:
            files.append(File(image_data, filename=image_filename))
            embed.set_image(url=f"attachment://{image_filename}")
        if video_data and video_filename:
            files.append(File(video_data, filename=video_filename))
            
        log_message(f"Sending message to Discord: {msg_link}", log_type="new_message")
        
        kwargs = {
            'username': author_name,
            'avatar_url': icon_url,
            'embed': embed
        }
        if files:
            kwargs['files'] = files
            
        success, too_large = send_webhook_message(WEBHOOK_URL, THREAD_ID, **kwargs)
        if not success:
            if too_large:
                log_message("Payload too large, falling back to sending raw links without attachments...", log_type="new_message")
                content_parts = []
                if msg_text:
                    content_parts.append(msg_text)
                
                # Add raw media links so Discord can auto-embed them
                if videos_to_send:
                    content_parts.append(videos_to_send[0])
                elif images_to_send:
                    content_parts.append(images_to_send[0])
                
                content_parts.append(f"[Message Link](<{msg_link}>)")
                
                fallback_content = "\n\n".join(content_parts)
                
                fallback_success, _ = send_webhook_message(
                    WEBHOOK_URL,
                    THREAD_ID,
                    username=author_name,
                    avatar_url=icon_url,
                    content=fallback_content
                )
                if fallback_success:
                    log_message("Sent plain text fallback successfully.", log_type="new_message")
                    return
            
            log_message("Failed to send main message", log_type="error")
            return
            
        if videos_to_send and not video_sent_as_attachment:
            video_url = videos_to_send[0]
            log_message(f"Sending raw video link as separate message: {video_url}", log_type="new_message")
            
            # Send raw video link so Discord auto-embeds the player
            send_webhook_message(
                WEBHOOK_URL, 
                THREAD_ID,
                username=author_name,
                avatar_url=icon_url,
                content=f"{video_url}\n[Message Link](<{msg_link}>)"
            )
            
        log_message("Message sent successfully.", log_type="new_message")
    except Exception as e:
        log_message(f"Error preparing or sending message to Discord: {e}", log_type="error")

def sendGroupedMediaMessage(msg_link: str, msg_text: str | None, images: list[str], videos: list[str], 
                            author_name: str, icon_url: str | None, timestamp: datetime.datetime | None = None) -> None:
    """Send multiple images/videos in a grouped message."""
    try:
        main_embed = Embed(title='Grouped Media Message Link', url=msg_link, color=EMBED_COLOR, timestamp=timestamp)
        description_parts = []
        if msg_text:
            description_parts.append(msg_text)
        description_parts.append(f"-# **Grouped Media:** {len(images)} images, {len(videos)} videos")
        main_embed.description = '\n\n'.join(description_parts)
        main_embed.set_author(name=author_name, icon_url=icon_url, url=msg_link)
        
        main_files = []
        if images:
            image_data, image_filename = download_image(images[0])
            if image_data and image_filename:
                main_files.append(File(image_data, filename=image_filename))
                main_embed.set_image(url=f"attachment://{image_filename}")
                
        log_message(f"Sending grouped media main message: {msg_link}", log_type="new_message")
        kwargs = {
            'username': author_name,
            'avatar_url': icon_url,
            'embed': main_embed
        }
        if main_files:
            kwargs['files'] = main_files
            
        success, too_large = send_webhook_message(WEBHOOK_URL, THREAD_ID, **kwargs)
        if not success:
            if too_large:
                log_message("Grouped media main message too large, falling back to sending raw links without attachments...", log_type="new_message")
                content_parts = []
                if msg_text:
                    content_parts.append(msg_text)
                
                # Add first media link
                media_link = images[0] if images else (videos[0] if videos else '')
                if media_link:
                    content_parts.append(media_link)
                
                content_parts.append(f"[Message Link](<{msg_link}>)")
                main_content = "\n\n".join(content_parts)
                
                send_webhook_message(
                    WEBHOOK_URL,
                    THREAD_ID,
                    username=author_name,
                    avatar_url=icon_url,
                    content=main_content
                )
            else:
                log_message("Failed to send grouped media main message", log_type="error")
                return
            
        # Send remaining images
        for i, image_url in enumerate(images[1:], 2):
            try:
                image_data, image_filename = download_image(image_url)
                if image_data and image_filename:
                    image_embed = Embed(title='Message Link', url=msg_link, color=EMBED_COLOR, timestamp=timestamp)
                    if msg_text:
                        image_embed.description = msg_text[:4096]
                    image_embed.set_author(name=author_name, icon_url=icon_url, url=msg_link)
                    image_embed.set_footer(text=f'Image {i} of {len(images)}')
                    image_embed.set_image(url=f"attachment://{image_filename}")
                    
                    success, too_large = send_webhook_message(
                        WEBHOOK_URL,
                        THREAD_ID,
                        username=author_name,
                        avatar_url=icon_url,
                        embed=image_embed,
                        files=[File(image_data, filename=image_filename)]
                    )
                    if not success:
                        if too_large:
                            log_message(f"Image {i} too large, falling back to link...", log_type="new_message")
                            image_content = f"**Image {i} of {len(images)}**:\n{image_url}\n[Message Link](<{msg_link}>)"
                            send_webhook_message(
                                WEBHOOK_URL,
                                THREAD_ID,
                                username=author_name,
                                avatar_url=icon_url,
                                content=image_content
                            )
                        else:
                            log_message(f"Failed to send image {i}", log_type="error")
            except Exception as e:
                log_message(f"Error sending image {i}: {e}", log_type="error")
                
        # Send videos
        for i, video_url in enumerate(videos, 1):
            try:
                video_sent_as_attachment = False
                try:
                    video_data, video_filename = download_video(video_url)
                    if video_data and video_filename:
                        log_message(f"Attempting to send video {i} as attachment: {video_url}", log_type="new_message")
                        video_embed = Embed(title='Message Link', url=msg_link, color=EMBED_COLOR, timestamp=timestamp)
                        if msg_text:
                            video_embed.description = msg_text[:4096]
                        video_embed.set_author(name=author_name, icon_url=icon_url, url=msg_link)
                        video_embed.set_footer(text=f'Video {i} of {len(videos)}')
                        
                        success, too_large = send_webhook_message(
                            WEBHOOK_URL,
                            THREAD_ID,
                            username=author_name,
                            avatar_url=icon_url,
                            embed=video_embed,
                            files=[File(video_data, filename=video_filename)]
                        )
                        if success:
                            video_sent_as_attachment = True
                            log_message(f"Video {i} sent successfully as attachment", log_type="new_message")
                        elif too_large:
                            log_message(f"Video {i} too large to attach, will fallback to raw link", log_type="new_message")
                except Exception as e:
                    log_message(f"Failed to send video {i} as attachment, falling back to link: {e}", log_type="error")
                    
                if not video_sent_as_attachment:
                    # Send raw video link so Discord auto-embeds the player
                    video_content = f"**Video {i} of {len(videos)}**:\n{video_url}\n[Message Link](<{msg_link}>)"
                    send_webhook_message(
                        WEBHOOK_URL,
                        THREAD_ID,
                        username=author_name,
                        avatar_url=icon_url,
                        content=video_content
                    )
            except Exception as e:
                log_message(f"Error sending video {i}: {e}", log_type="error")
                
        log_message(f"Grouped media message sent successfully: {len(images)} images, {len(videos)} videos", log_type="new_message")
    except Exception as e:
        log_message(f"Error sending grouped media message: {e}", log_type="error")

def sendMissingMessages(channel: str, missing_numbers: list[int], author_name: str, icon_url: str | None, timestamp: datetime.datetime | None) -> None:
    """Send placeholders for specific missing message numbers."""
    for missing_number in missing_numbers:
        missing_link = f"https://t.me/{channel}/{missing_number}"
        log_message(f"Sending placeholder for missing message: {missing_link}", log_type="error")
        sendMessage(missing_link, ERROR_PLACEHOLDER, None, None, author_name, icon_url, timestamp=timestamp)

def main(tg_channel: str) -> None:
    SCRIPT_START_TIME = datetime.datetime.now()
    msg_log = []
    last_processed_number = 0
    grouped_media_ranges = set()
    log_message(f"Starting bot for channel: {tg_channel}", log_type="status2")

    while True:
        try:
            msg_temp = []
            log_message("Checking for new messages...", log_type="status2")
            message_boxes = scrapeTelegramMessageBox(tg_channel)
            if not message_boxes:
                continue
            for tg_box in message_boxes:
                msg_link = getLink(tg_box)
                if not msg_link:
                    continue

                match = re.match(rf"https://t.me/{tg_channel}/(\d+)", msg_link)
                if not match:
                    continue

                current_number = int(match.group(1))
                author_name = getAuthorName(tg_box)
                icon_url = getAuthorIcon(tg_box)
                timestamp = getTimestamp(tg_box)

                if current_number in grouped_media_ranges:
                    log_message(f"Skipping grouped media component: {msg_link}", log_type="status2")
                    msg_temp.append(msg_link)
                    last_processed_number = current_number
                    continue

                if last_processed_number > 0 and current_number > last_processed_number + 1:
                    filtered_missing = [num for num in range(last_processed_number + 1, current_number) if num not in grouped_media_ranges]
                    if filtered_missing:
                        sendMissingMessages(tg_channel, filtered_missing, author_name, icon_url, timestamp)

                if is_message_logged(tg_channel, current_number):
                    log_message(f"Skipping already logged message: {msg_link}", log_type="status2")
                    continue

                msg_text = getText(tg_box)
                msg_image = getImage(tg_box)
                msg_video = getVideo(tg_box)
                
                all_images = getAllImages(tg_box)
                all_videos = getAllVideos(tg_box)
                total_media = len(all_images) + len(all_videos)
                
                if total_media > 1 and not msg_text:
                    log_message(f"Grouped media detected with no text, trying individual message URL: {msg_link}", log_type="status2")
                    msg_text = getTextFromIndividualMessage(msg_link)
                    if msg_text:
                        log_message(f"Successfully extracted text from meta tags: '{msg_text[:50]}...'", log_type="status2")

                if msg_link not in msg_log:
                    log_message(f"New message found: {msg_link}", log_type="new_message")
                    msg_temp.append(msg_link)
                    
                    if total_media > 1:
                        log_message(f"Marking grouped media range: {current_number} + {total_media-1} components", log_type="status2")
                        for i in range(1, total_media):
                            grouped_media_ranges.add(current_number + i)
                    
                    sendMessage(msg_link, msg_text, msg_image, msg_video, author_name, icon_url, timestamp=timestamp, all_images=all_images, all_videos=all_videos)

                msg_temp.append(msg_link)
                last_processed_number = current_number

            msg_log = msg_temp
            current_time = datetime.datetime.now()
            time_passed = current_time - SCRIPT_START_TIME
            log_message(f"Bot working for {tg_channel}. Time passed: {time_passed}", log_type="status")
        except Exception as e:
            log_message(f"[   E R R O R   ]\n{e}\nScript ignored the error and keeps running.", log_type="error")
        time.sleep(COOLDOWN)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        log_message("Usage: python webhook.py <TG_CHANNEL>", log_type="status2") 
        sys.exit(1)
    TG_CHANNEL = sys.argv[1]
    log_message(f"Initializing bot with channel: {TG_CHANNEL}", log_type="status2")
    main(TG_CHANNEL)