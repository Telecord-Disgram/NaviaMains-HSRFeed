import subprocess
import time
from config import Channels, WEBHOOK_URL, THREAD_ID

processes = []
try:
    if THREAD_ID != None:
        for channel in Channels:
            print(f"Starting bot for {channel}...")
            channel = channel[13:]
            process = subprocess.Popen(["python", "threadhook.py", channel, WEBHOOK_URL + f"?thread_id={THREAD_ID}"])
            processes.append(process)

        print("Bots are running. Press Ctrl + C to stop.")
        
        while True:
            time.sleep(1)
            
    else:
        for channel in Channels:
            print(f"Starting bot for {channel}...")
            channel = channel[13:]
            process = subprocess.Popen(["python", "webhook.py", channel])
            processes.append(process)

        print("Bots are running. Press Ctrl + C to stop.")
        
        while True:
            time.sleep(1)

except KeyboardInterrupt:
    print("\nShutting down all bots...")
    for process in processes:
        process.terminate()
    for process in processes:
        process.wait()
    print("All bots have been stopped.")