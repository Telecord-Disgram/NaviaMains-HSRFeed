import subprocess
import time
import threading
import datetime
import os
import psutil
import requests
import re
from flask import Flask, jsonify, Response
from config import Channels, WEBHOOK_URL, THREAD_ID

processes = []
bot_start_time = None
last_health_check = None
health_status = {"status": "starting", "details": {}}

app = Flask(__name__)

def initialize_disgram_log():
    existing_links = set()
    if os.path.exists("Disgram.log"):
        with open("Disgram.log", "r", encoding="utf-8") as log_file:
            for line in log_file:
                line = line.strip()
                if line.startswith("https://t.me/"):
                    existing_links.add(line)
                    
    new_links = []
    for channel_url in Channels:
        if channel_url not in existing_links:
            new_links.append(channel_url)
    
    if new_links:
        with open("Disgram.log", "a", encoding="utf-8") as log_file:
            for channel_url in new_links:
                log_file.write(f"{channel_url}\n")

def extract_channel_name(channel_url):
    if channel_url.startswith("https://t.me/"):
        path = channel_url[13:]
        channel_name = path.split("/")[0]
        return channel_name
    else:
        return channel_url

def check_process_health():
    alive_processes = 0
    dead_processes = []
    
    for i, process in enumerate(processes):
        if process and process.poll() is None:
            alive_processes += 1
        else:
            dead_processes.append(i)
    
    return alive_processes, dead_processes

def check_telegram_connectivity():
    try:
        response = requests.get("https://t.me/", timeout=10)
        return response.status_code == 200
    except Exception:
        return False

def check_discord_webhook():
    if not WEBHOOK_URL or "{webhookID}" in WEBHOOK_URL:
        return False, "Webhook URL not configured"
    
    try:
        response = requests.get(WEBHOOK_URL, timeout=10)
        if response.status_code == 200:
            return True, "Webhook accessible"
        else:
            return False, f"Webhook returned status {response.status_code}"
    except Exception as e:
        return False, f"Webhook error: {str(e)}"

def check_log_freshness():
    log_file_path = "Disgram.log"
    max_age_minutes = 6  # Consider unhealthy if log is older than 6 minutes
    
    try:
        if not os.path.exists(log_file_path):
            return False, "Log file does not exist", None
        
        last_modified = os.path.getmtime(log_file_path)
        last_modified_dt = datetime.datetime.fromtimestamp(last_modified)
        
        current_time = datetime.datetime.now()
        age_minutes = (current_time - last_modified_dt).total_seconds() / 60
        
        is_fresh = age_minutes <= max_age_minutes
        
        if is_fresh:
            return True, f"Log is fresh (last updated {age_minutes:.1f} minutes ago)", last_modified_dt
        else:
            return False, f"Log is stale (last updated {age_minutes:.1f} minutes ago, max allowed: {max_age_minutes})", last_modified_dt
            
    except Exception as e:
        return False, f"Error checking log freshness: {str(e)}", None

def get_system_stats():
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_available_mb": round(memory.available / 1024 / 1024, 2),
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 2)
        }
    except Exception as e:
        return {"error": str(e)}

def restart_all_processes():
    """Restart all bot processes when they appear to be zombified"""
    global processes, bot_start_time
    
    print("⚠️  Log freshness check failed - restarting all bot processes...")
    
    # Terminate existing processes
    for process in processes:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception as e:
                print(f"Error terminating process: {e}")
    
    # Clear the processes list
    processes.clear()
    
    # Restart all processes
    start_bot_processes()
    
    print(f"✅ Restarted {len(processes)} bot processes due to stale logs")

@app.route('/health')
def health_check():
    global last_health_check
    last_health_check = datetime.datetime.now()
    
    alive_count, dead_processes = check_process_health()
    total_processes = len(processes)
    
    telegram_ok = check_telegram_connectivity()
    discord_ok, discord_msg = check_discord_webhook()
    
    # Check log freshness (critical for detecting zombie processes)
    log_fresh, log_msg, log_last_modified = check_log_freshness()
    
    system_stats = get_system_stats()
    
    uptime_seconds = (datetime.datetime.now() - bot_start_time).total_seconds() if bot_start_time else 0
    uptime_minutes = round(uptime_seconds / 60, 2)
    
    is_healthy = (
        alive_count == total_processes and
        alive_count > 0 and
        telegram_ok and
        discord_ok and
        log_fresh
    )
    
    status_code = 200 if is_healthy else 503
    
    # Get rate limiting status
    try:
        from rate_limiter import discord_rate_limiter
        rate_limit_status = discord_rate_limiter.get_rate_limit_status()
    except Exception as e:
        rate_limit_status = {"error": f"Failed to get rate limit status: {str(e)}"}
    
    health_data = {
        "status": "healthy" if is_healthy else "unhealthy",
        "timestamp": last_health_check.isoformat(),
        "uptime_minutes": uptime_minutes,
        "processes": {
            "total": total_processes,
            "running": alive_count,
            "dead": dead_processes,
            "channels": [extract_channel_name(ch) for ch in Channels]
        },
        "external_services": {
            "telegram_reachable": telegram_ok,
            "discord_webhook": {
                "accessible": discord_ok,
                "message": discord_msg
            }
        },
        "log_freshness": {
            "is_fresh": log_fresh,
            "message": log_msg,
            "last_modified": log_last_modified.isoformat() if log_last_modified else None,
            "age_minutes": round((datetime.datetime.now() - log_last_modified).total_seconds() / 60, 1) if log_last_modified else None
        },
        "system": system_stats,
        "rate_limiting": rate_limit_status,
        "configuration": {
            "thread_id_configured": THREAD_ID is not None,
            "webhook_configured": WEBHOOK_URL and "{webhookID}" not in WEBHOOK_URL,
            "channels_count": len(Channels)
        }
    }
    
    global health_status
    health_status = health_data
    
    return jsonify(health_data), status_code

@app.route('/logs')
def view_logs():
    try:
        log_file_path = "Disgram.log"
        
        if not os.path.exists(log_file_path):
            return Response(
                "Disgram.log file not found",
                status=404,
                mimetype='text/plain'
            )
        
        with open(log_file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            
        last_lines = lines[-1000:] if len(lines) > 1000 else lines
        
        log_content = ''.join(last_lines)
        
        total_lines = len(lines)
        showing_lines = len(last_lines)
        header = f"Disgram Log Viewer\n"
        header += f"Total lines in log: {total_lines}\n"
        header += f"Showing last {showing_lines} lines\n"
        header += f"Log file: {os.path.abspath(log_file_path)}\n"
        header += f"Last modified: {datetime.datetime.fromtimestamp(os.path.getmtime(log_file_path)).isoformat()}\n"
        header += "=" * 80 + "\n\n"
        
        response_content = header + log_content
        
        return Response(
            response_content,
            mimetype='text/plain',
            headers={
                'Content-Type': 'text/plain; charset=utf-8',
                'Cache-Control': 'no-cache'
            }
        )
        
    except Exception as e:
        return Response(
            f"Error reading log file: {str(e)}",
            status=500,
            mimetype='text/plain'
        )

@app.route('/')
def root():
    return jsonify({
        "name": "Disgram",
        "description": "Telegram to Discord messages forwarding bot",
        "health_endpoint": "/health",
        "logs_endpoint": "/logs",
        "channels": len(Channels),
        "status": health_status.get("status", "unknown")
    })

def start_bot_processes():
    global bot_start_time, processes
    bot_start_time = datetime.datetime.now()
    
    # Initialize Disgram.log with channel/message links from environment
    initialize_disgram_log()
    
    print(f"Starting Disgram bot with {len(Channels)} channels...")
    
    try:
        if THREAD_ID is not None:
            for channel in Channels:
                print(f"Starting threaded bot for {channel}...")
                channel_name = extract_channel_name(channel)
                process = subprocess.Popen(
                    ["python", "threadhook.py", channel_name, f"{WEBHOOK_URL}?thread_id={THREAD_ID}"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                processes.append(process)
        else:
            for channel in Channels:
                print(f"Starting webhook bot for {channel}...")
                channel_name = extract_channel_name(channel)
                process = subprocess.Popen(
                    ["python", "webhook.py", channel_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                processes.append(process)
        
        print(f"Started {len(processes)} bot processes successfully.")
        
    except Exception as e:
        print(f"Error starting bot processes: {e}")

def run_flask_server():
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting health check server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    import os
    
    start_bot_processes()
    
    flask_thread = threading.Thread(target=run_flask_server, daemon=True)
    flask_thread.start()
    
    print("Disgram bot is running with health check endpoint.")
    print("Health check available at: /health")
    print("Log viewer available at: /logs")
    
    try:
        while True:
            time.sleep(30)
            
            alive_count, dead_processes = check_process_health()
            if dead_processes:
                print(f"Detected {len(dead_processes)} dead processes, restarting...")
                for dead_idx in dead_processes:
                    if dead_idx < len(processes) and dead_idx < len(Channels):
                        channel = Channels[dead_idx]
                        channel_name = extract_channel_name(channel)
                        print(f"Restarting process for {channel}...")
                        
                        if THREAD_ID is not None:
                            new_process = subprocess.Popen(
                                ["python", "threadhook.py", channel_name, f"{WEBHOOK_URL}?thread_id={THREAD_ID}"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                        else:
                            new_process = subprocess.Popen(
                                ["python", "webhook.py", channel_name],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                        processes[dead_idx] = new_process
            
            # Check if logs are stale (indicates zombie processes)
            log_fresh, log_msg, log_last_modified = check_log_freshness()
            if not log_fresh and alive_count > 0:  # Only restart if we have processes that should be working
                print(f"🚨 ZOMBIE PROCESSES DETECTED: {log_msg}")
                print("All processes appear alive but logs are stale - restarting all processes...")
                restart_all_processes()
            
    except KeyboardInterrupt:
        print("\nShutting down all bots...")
        for process in processes:
            if process and process.poll() is None:
                process.terminate()
        
        for process in processes:
            if process:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        
        print("All bots have been stopped.")