import time
import datetime
import requests
import sys
import re
import os
import io
from dateutil import parser
from config import WEBHOOK_URL, COOLDOWN, EMBED_COLOR
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
    return converted_text

def getImage(tg_box):
    msg_image = tg_box.find('a', {'class': 'tgme_widget_message_photo_wrap'}, href=True)
    if msg_image:
        startIndex = msg_image['style'].find("background-image:url('") + 22
        endIndex = msg_image['style'].find(".jpg')") + 4
        if startIndex > 21 and endIndex > 3:
            return msg_image['style'][startIndex:endIndex]
    return None

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

def sendMessage(msg_link, msg_text, msg_image, msg_video, author_name, icon_url, timestamp=None):
    max_retries = 5
    retry_delay = 2
    
    image_data = None
    image_filename = None
    
    if msg_image:
        image_data, image_filename = download_image(msg_image)
    
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
            
            if msg_video:
                video_content = f"[Attached video]({msg_video})\n[Message Link](<{msg_link}>)"
                log_message(f"Sending video link as separate message: {msg_video}", log_type="new_message")
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

def sendMissingMessages(channel, last_number, current_number, author_name, icon_url):
    for missing_number in range(last_number + 1, current_number):
        missing_link = f"https://t.me/{channel}/{missing_number}"
        log_message(f"Sending placeholder for missing message: {missing_link}", log_type="error")
        sendMessage(missing_link, None, [], author_name, icon_url)

def main(tg_channel):
    SCRIPT_START_TIME = datetime.datetime.now()
    msg_log = []
    last_processed_number = 0
    log_message(f"Starting bot for channel: {tg_channel}", log_type="status2")

    while True:
        try:
            msg_temp = []
            log_message("Checking for new messages...", log_type="status2")
            for tg_box in scrapeTelegramMessageBox(tg_channel):
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

                if last_processed_number > 0 and current_number > last_processed_number + 1:
                    sendMissingMessages(tg_channel, last_processed_number, current_number, author_name, icon_url)

                if is_message_logged(tg_channel, current_number):
                    log_message(f"Skipping already logged message: {msg_link}", log_type="status2")
                    continue

                msg_text = getText(tg_box)
                msg_image = getImage(tg_box)
                msg_video = getVideo(tg_box)

                if msg_link not in msg_log:
                    log_message(f"New message found: {msg_link}", log_type="new_message")
                    msg_temp.append(msg_link)
                    sendMessage(msg_link, msg_text, msg_image, msg_video, author_name, icon_url, timestamp=timestamp)

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