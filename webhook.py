import time
import datetime
import requests
import sys
import re
import os
import io
from dateutil import parser
from config import WEBHOOK_URL, COOLDOWN, EMBED_COLOR, ERROR_PLACEHOLDER
from bs4 import BeautifulSoup
from discord import SyncWebhook, Embed, File

def log_message(message, log_type="info"):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} {message}"
    print(log_entry)
    if log_type in ["error", "new_message", "status"]:
        with open("Disgram.log", "a") as log_file:
            log_file.write(log_entry + "\n")

def is_message_logged(channel, number):
    try:
        with open("Disgram.log", "r") as log_file:
            for line in log_file:
                match = re.search(rf"https://t.me/{channel}/(\d+)", line)
                if match and int(match.group(1)) >= int(number):
                    return True
    except FileNotFoundError:
        pass
    return False

def scrapeTelegramMessageBox(channel):
    max_retries = 5
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            log_message(f"Scraping messages from Telegram channel: {channel} (Attempt {attempt + 1})")
            tg_html = requests.get(f'https://t.me/s/{channel}', timeout=10)
            tg_html.raise_for_status()
            tg_soup = BeautifulSoup(tg_html.text, 'html.parser')
            tg_box = tg_soup.find_all('div', {'class': 'tgme_widget_message_wrap js-widget_message_wrap'})
            return tg_box
        except requests.exceptions.RequestException as e:
            log_message(f"Error scraping Telegram: {e}", log_type="error")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                log_message("Max retries reached. Skipping this iteration.", log_type="error")
                return []

def getAuthorIcon(tg_box):
    icon_element = tg_box.find('i', {'class': 'tgme_widget_message_user_photo'})
    if icon_element:
        img_tag = icon_element.find('img')
        if img_tag and 'src' in img_tag.attrs:
            return img_tag['src']
    return None

def getAuthorName(tg_box):
    author_name = tg_box.find('a', {'class': 'tgme_widget_message_owner_name'})
    return author_name.text.strip() if author_name else None

def getLink(tg_box):
    msg_link = tg_box.find_all('a', {'class':'tgme_widget_message_date'}, href=True)
    if msg_link:
        return msg_link[0]['href']
    return None

def getText(tg_box):
    msg_text = tg_box.find_all('div', {'class': 'tgme_widget_message_text js-message_text'})
    converted_text = ''
    if not msg_text:
        return None

    msg_text = msg_text[0]
    for child in msg_text.children:
        if child.name is None:
            converted_text += child
        elif child.name == 'a':
            if child.text == child['href']:
                converted_text += child['href']
            else:
                converted_text += f"[{child.text}]({child['href']})"
        elif child.name == 'pre':
            converted_text += f"```{child.text}```"
        elif child.name == 'b':
            converted_text += f"**{child.text}**"
        elif child.name == 'tg-spoiler':
            converted_text += f"||{child.text}||"
        elif child.name == 'i':
            converted_text += f"*{child.text}*"
        elif child.name == 'u':
            converted_text += f"__{child.text}__"
        elif child.name == 's':
            converted_text += f"~~{child.text}~~"
        elif child.name == 'br':
            converted_text += '\n'
        elif child.name == 'blockquote':
            converted_text += f"> {child.text}\n"
    return converted_text

def getTextFromIndividualMessage(msg_link):
    """Extract text from an individual message URL, useful for grouped media messages"""
    if not msg_link:
        return None
        
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            response = requests.get(msg_link, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # First try to find text in standard location
            text_div = soup.find('div', class_='tgme_widget_message_text')
            if text_div:
                text_content = text_div.get_text(strip=True)
                if text_content:
                    return text_content
            
            # For grouped media messages, check meta tags
            og_desc = soup.find('meta', property='og:description')
            if og_desc:
                content_attr = og_desc.get('content')
                if content_attr:
                    # Handle both string and list types
                    content = str(content_attr).strip() if hasattr(content_attr, 'strip') else str(content_attr)
                    if content and _is_likely_message_content(content):
                        return content
                    
            return None
            
        except Exception as e:
            log_message(f"Error fetching text from individual message {msg_link}: {e}", log_type="error")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return None

def _is_likely_message_content(content):
    """Simple check to filter out obvious channel descriptions"""
    if not content:
        return False
    
    content_lower = content.lower().strip()
    
    # Filter out common channel description patterns
    channel_desc_patterns = [
        r'^the official .+ on telegram',
        r'official .+ channel',
        r'.+ official channel', 
        r'welcome to .+',
        r'much recursion\. very telegram\. wow\.',  # Telegram's description
        r'^.+\s+–\s+.+$',  # Channel title format
    ]
    
    for pattern in channel_desc_patterns:
        if re.match(pattern, content_lower):
            return False
    
    # If content is very generic/short, be cautious
    if len(content.split()) <= 1:
        return False
    
    # Otherwise, likely message content
    return True

def getImage(tg_box):
    msg_image = tg_box.find('a', {'class': 'tgme_widget_message_photo_wrap'}, href=True)
    if msg_image:
        startIndex = msg_image['style'].find("background-image:url('") + 22
        endIndex = msg_image['style'].find(".jpg')") + 4
        if startIndex > 21 and endIndex > 3:
            return msg_image['style'][startIndex:endIndex]
    return None

def getAllImages(tg_box):
    """Extract all images from a message (for grouped media)"""
    images = []
    msg_images = tg_box.find_all('a', {'class': 'tgme_widget_message_photo_wrap'})
    
    for msg_image in msg_images:
        if msg_image.get('style'):
            style = msg_image['style']
            # Handle different image formats (.jpg, .png, .webp, etc.)
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                start_pos = style.find("background-image:url('")
                end_pos = style.find(f"{ext}')")
                if start_pos > -1 and end_pos > -1:
                    start_index = start_pos + 22
                    end_index = end_pos + len(ext)
                    if start_index > 21 and end_index > start_index:
                        image_url = style[start_index:end_index]
                        images.append(image_url)
                    break
    
    return images

def getAllVideos(tg_box):
    """Extract all videos from a message (for grouped media)"""
    videos = []
    video_elements = tg_box.find_all('video', {'class': 'tgme_widget_message_video'})
    
    for video_element in video_elements:
        if video_element.get('src'):
            videos.append(video_element['src'])
    
    return videos

def getTimestamp(tg_box):
    time_element = tg_box.find('time', {'datetime': True})
    if time_element and 'datetime' in time_element.attrs:
        return parser.isoparse(time_element['datetime'])
    return None

def download_image(image_url):
    if not image_url:
        return None, None
    
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            
            file_ext = os.path.splitext(image_url)[1]
            if not file_ext:
                file_ext = '.jpg'
                
            filename = f"img_{int(time.time())}_{attempt}{file_ext}"
            return io.BytesIO(response.content), filename
        except Exception as e:
            log_message(f"Error downloading image: {e}", log_type="error")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                log_message("Max retries reached. Unable to download image.", log_type="error")
                return None, None

def getVideo(tg_box):
    video_element = tg_box.find('video', {'class': 'tgme_widget_message_video'})
    if video_element and 'src' in video_element.attrs:
        return video_element['src']
    return None

def sendMessage(msg_link, msg_text, msg_image, msg_video, author_name, icon_url, timestamp=None, all_images=None, all_videos=None):
    max_retries = 5
    retry_delay = 2
    
    # Use all_images if provided (for grouped media), otherwise fall back to single image
    images_to_send = all_images if all_images else ([msg_image] if msg_image else [])
    videos_to_send = all_videos if all_videos else ([msg_video] if msg_video else [])
    
    # If this is a grouped media message, send all media items
    if len(images_to_send) > 1 or len(videos_to_send) > 1:
        log_message(f"Sending grouped media message with {len(images_to_send)} images and {len(videos_to_send)} videos: {msg_link}", log_type="new_message")
        sendGroupedMediaMessage(msg_link, msg_text, images_to_send, videos_to_send, author_name, icon_url, timestamp)
        return
    
    # Original single media logic
    image_data = None
    image_filename = None
    
    if images_to_send:
        result = download_image(images_to_send[0])
        if result:
            image_data, image_filename = result
        else:
            image_data, image_filename = None, None
    
    for attempt in range(max_retries):
        try:
            webhook = SyncWebhook.from_url(WEBHOOK_URL)
            
            embed = Embed(title='Message Link', url=msg_link, color=EMBED_COLOR, timestamp=timestamp)
            
            if msg_text:
                embed.description = msg_text
            
            embed.set_author(name=author_name, icon_url=icon_url, url=msg_link)
            
            files = []
            if image_data and image_filename:
                file = File(image_data, filename=image_filename)
                files.append(file)
                embed.set_image(url=f"attachment://{image_filename}")
            
            log_message(f"Sending message to Discord: {msg_link}", log_type="new_message")
            
            if files:
                webhook.send(username=author_name, avatar_url=icon_url, embed=embed, files=files)
            else:
                webhook.send(username=author_name, avatar_url=icon_url, embed=embed)
            
            if videos_to_send:
                video_content = f"[Attached video]({videos_to_send[0]})\n[Message Link](<{msg_link}>)"
                log_message(f"Sending video link as separate message: {videos_to_send[0]}", log_type="new_message")
                time.sleep(0.4)
                webhook.send(username=author_name, avatar_url=icon_url, content=video_content)
            
            log_message("Message sent successfully.", log_type="new_message")
            time.sleep(0.4)
            return
            
        except requests.exceptions.RequestException as e:
            log_message(f"Error sending message to Discord: {e}", log_type="error")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                log_message("Max retries reached. Message not sent.", log_type="error")

def sendGroupedMediaMessage(msg_link, msg_text, images, videos, author_name, icon_url, timestamp=None):
    """Send a grouped media message with multiple images/videos"""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            webhook = SyncWebhook.from_url(WEBHOOK_URL)
            
            # Send the main message with text and first image
            embed = Embed(title='Grouped Media Message Link', url=msg_link, color=EMBED_COLOR, timestamp=timestamp)
            
            description_parts = []
            if msg_text:
                description_parts.append(msg_text)
            
            description_parts.append(f"📁 **Grouped Media:** {len(images)} images, {len(videos)} videos")
            
            embed.description = '\n\n'.join(description_parts)
            embed.set_author(name=author_name, icon_url=icon_url, url=msg_link)
            
            # Add first image to the main embed if available
            files = []
            if images:
                result = download_image(images[0])
                if result:
                    image_data, image_filename = result
                else:
                    image_data, image_filename = None, None
                if image_data and image_filename:
                    file = File(image_data, filename=image_filename)
                    files.append(file)
                    embed.set_image(url=f"attachment://{image_filename}")
            
            # Send main message
            if files:
                webhook.send(username=author_name, avatar_url=icon_url, embed=embed, files=files)
            else:
                webhook.send(username=author_name, avatar_url=icon_url, embed=embed)
            
            time.sleep(0.5)
            
            # Send additional images (skip first one as it's already sent)
            for i, image_url in enumerate(images[1:], 2):
                try:
                    result = download_image(image_url)
                    if result:
                        image_data, image_filename = result
                        if image_data and image_filename:
                            image_embed = Embed(color=EMBED_COLOR)
                            image_embed.set_image(url=f"attachment://{image_filename}")
                            image_embed.set_footer(text=f'Image {i} of {len(images)}')
                            
                            image_file = File(image_data, filename=image_filename)
                            webhook.send(username=author_name, avatar_url=icon_url, embed=image_embed, files=[image_file])
                        time.sleep(0.3)
                except Exception as e:
                    log_message(f"Error sending image {i}: {e}", log_type="error")
            
            # Send videos as links
            for i, video_url in enumerate(videos, 1):
                try:
                    video_content = f"🎥 **Video** [**{i}**]({video_url}) of {len(videos)}\n[Message Link](<{msg_link}>)"
                    webhook.send(username=author_name, avatar_url=icon_url, content=video_content)
                    time.sleep(0.3)
                except Exception as e:
                    log_message(f"Error sending video {i}: {e}", log_type="error")
            
            log_message(f"Grouped media message sent successfully: {len(images)} images, {len(videos)} videos", log_type="new_message")
            return
            
        except requests.exceptions.RequestException as e:
            log_message(f"Error sending grouped media message: {e}", log_type="error")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                log_message("Max retries reached. Grouped media message not sent.", log_type="error")

def sendMissingMessages(channel, last_number, current_number, author_name, icon_url, timestamp):
    for missing_number in range(last_number + 1, current_number):
        missing_link = f"https://t.me/{channel}/{missing_number}"
        log_message(f"Sending placeholder for missing message: {missing_link}", log_type="error")
        sendMessage(missing_link, ERROR_PLACEHOLDER, None, None, author_name, icon_url, timestamp=timestamp)

def sendMissingMessagesFiltered(channel, missing_numbers, author_name, icon_url, timestamp):
    """Send placeholders for specific missing message numbers (filtered to exclude grouped media components)"""
    for missing_number in missing_numbers:
        missing_link = f"https://t.me/{channel}/{missing_number}"
        log_message(f"Sending placeholder for missing message: {missing_link}", log_type="error")
        sendMessage(missing_link, ERROR_PLACEHOLDER, None, None, author_name, icon_url, timestamp=timestamp)

def main(tg_channel):
    SCRIPT_START_TIME = datetime.datetime.now()
    msg_log = []
    last_processed_number = 0
    grouped_media_ranges = set()  # Track message numbers that are part of grouped media
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

                # Check if this message is part of a grouped media we already processed
                if current_number in grouped_media_ranges:
                    log_message(f"Skipping grouped media component: {msg_link}", log_type="status2")
                    msg_temp.append(msg_link)
                    last_processed_number = current_number
                    continue

                if last_processed_number > 0 and current_number > last_processed_number + 1:
                    # Filter out grouped media components from missing messages
                    filtered_missing = []
                    for missing_num in range(last_processed_number + 1, current_number):
                        if missing_num not in grouped_media_ranges:
                            filtered_missing.append(missing_num)
                    
                    if filtered_missing:
                        sendMissingMessagesFiltered(tg_channel, filtered_missing, author_name, icon_url, timestamp)

                if is_message_logged(tg_channel, current_number):
                    log_message(f"Skipping already logged message: {msg_link}", log_type="status2")
                    continue

                msg_text = getText(tg_box)
                msg_image = getImage(tg_box)
                msg_video = getVideo(tg_box)
                
                # Check for grouped media
                all_images = getAllImages(tg_box)
                all_videos = getAllVideos(tg_box)
                
                # Calculate total media count
                total_media = len(all_images) + len(all_videos)
                
                # For grouped media messages, if no text found in the box, try individual message URL
                if total_media > 1 and not msg_text:
                    log_message(f"Grouped media detected with no text, trying individual message URL: {msg_link}", log_type="status2")
                    msg_text = getTextFromIndividualMessage(msg_link)
                    if msg_text:
                        log_message(f"Successfully extracted text from meta tags: '{msg_text[:50]}...'", log_type="status2")

                if msg_link not in msg_log:
                    log_message(f"New message found: {msg_link}", log_type="new_message")
                    msg_temp.append(msg_link)
                    
                    # If this is grouped media, mark the component message numbers
                    if total_media > 1:
                        log_message(f"Marking grouped media range: {current_number} + {total_media-1} components", log_type="status2")
                        for i in range(1, total_media):  # Skip first message (already processed), mark next N-1
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