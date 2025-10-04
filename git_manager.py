"""
Git manager for Disgram log persistence via repository commits
"""
import os
import time
import threading
import subprocess
import logging
from typing import Optional
from datetime import datetime

# Get logger (configured in main.py)
logger = logging.getLogger('GitManager')

def sanitize_url_for_logging(url: str) -> str:
    """Remove sensitive tokens from URLs for safe logging"""
    if not url:
        return url
    
    import re
    # Replace GitHub Personal Access Tokens with [REDACTED]
    # Pattern matches: github_pat_[alphanumeric] or ghp_[alphanumeric]
    sanitized = re.sub(r'github_pat_[A-Za-z0-9_]+', '[REDACTED]', url)
    sanitized = re.sub(r'ghp_[A-Za-z0-9_]+', '[REDACTED]', sanitized)
    
    # Also handle generic token patterns like :token@
    sanitized = re.sub(r'://[^@\s]+@', '://[REDACTED]@', sanitized)
    
    return sanitized

class GitLogManager:
    def __init__(self, github_token: Optional[str] = None, commit_interval: int = 2700):
        self.github_token = github_token
        self.commit_interval = commit_interval  # For interval mode
        self.local_log_path = "Disgram.log"
        self.commit_lock = threading.Lock()
        
        # Commit mode configuration
        self.commit_mode = os.getenv("COMMIT_MODE", "interval").lower()
        self.commit_schedule = os.getenv("COMMIT_SCHEDULE", "hourly").lower()
        self.custom_hours = self._parse_custom_hours(os.getenv("COMMIT_CUSTOM_HOURS", "0,6,12,18"))
        self.startup_grace = int(os.getenv("STARTUP_GRACE_PERIOD", "600"))
        
        # Initialize last_commit_time by checking recent Git history
        self.last_commit_time = self._get_last_commit_time()
        
        # Add startup grace period to prevent immediate commits
        current_time = time.time()
        if (current_time - self.last_commit_time) < self.startup_grace:
            logger.info(f"Recent commit detected, extending cooldown by {self.startup_grace//60} minutes")
            self.last_commit_time = current_time  # Reset to prevent immediate commit
        
        # Configure git if token is provided
        if self.github_token:
            self._configure_git_auth()
        
        # Start background commit thread
        self.commit_thread = threading.Thread(target=self._background_commit, daemon=True)
        self.commit_thread.start()
        
        # Log initialization details
        if self.commit_mode == "scheduled":
            schedule_desc = self._get_schedule_description()
            logger.info(f"GitLogManager initialized - mode: scheduled ({schedule_desc}), last commit: {(current_time - self.last_commit_time)//60:.1f} minutes ago")
        else:
            logger.info(f"GitLogManager initialized - mode: interval ({commit_interval//60} minutes), last commit: {(current_time - self.last_commit_time)//60:.1f} minutes ago")
    
    def _parse_custom_hours(self, hours_str: str) -> list:
        """Parse custom hours from environment variable"""
        try:
            hours = [int(h.strip()) for h in hours_str.split(',') if h.strip()]
            return [h for h in hours if 0 <= h <= 23]  # Validate range
        except (ValueError, AttributeError):
            logger.warning(f"Invalid COMMIT_CUSTOM_HOURS format: {hours_str}, using default")
            return [0, 6, 12, 18]
    
    def _get_schedule_description(self) -> str:
        """Get human-readable schedule description"""
        if self.commit_schedule == "hourly":
            return "every hour"
        elif self.commit_schedule == "every_2h":
            return "every 2 hours"
        elif self.commit_schedule == "custom":
            return f"at hours: {', '.join(map(str, sorted(self.custom_hours)))}"
        else:
            return "hourly (fallback)"
    
    def _get_next_scheduled_time(self) -> Optional[float]:
        """Get the next scheduled commit time in UTC timestamp"""
        from datetime import datetime, timezone, timedelta
        
        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        current_minute = now_utc.minute
        
        # Determine target hours based on schedule
        if self.commit_schedule == "hourly":
            target_hours = list(range(24))  # Every hour
        elif self.commit_schedule == "every_2h":
            target_hours = list(range(0, 24, 2))  # 0, 2, 4, 6, ..., 22
        elif self.commit_schedule == "custom":
            target_hours = sorted(self.custom_hours)
        else:
            target_hours = list(range(24))  # Fallback to hourly
        
        # Find next scheduled hour
        next_hour = None
        for hour in target_hours:
            if hour > current_hour or (hour == current_hour and current_minute < 5):
                # Allow 5-minute window at the start of each hour
                next_hour = hour
                break
        
        if next_hour is None:
            # No more hours today, get first hour of tomorrow
            next_hour = target_hours[0]
            now_utc += timedelta(days=1)
        
        # Create next scheduled time (at the start of the hour)
        next_time = now_utc.replace(hour=next_hour, minute=0, second=0, microsecond=0)
        return next_time.timestamp()
    
    def _is_scheduled_time(self) -> bool:
        """Check if current time matches scheduled commit time"""
        from datetime import datetime, timezone
        
        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        current_minute = now_utc.minute
        
        # Only commit in the first 5 minutes of the scheduled hour
        if current_minute >= 5:
            return False
        
        # Determine if current hour is scheduled
        if self.commit_schedule == "hourly":
            return True  # Every hour
        elif self.commit_schedule == "every_2h":
            return current_hour % 2 == 0  # Even hours only
        elif self.commit_schedule == "custom":
            return current_hour in self.custom_hours
        else:
            return True  # Fallback to hourly
    
    def _configure_git_auth(self):
        """Configure git authentication using GitHub token"""
        try:
            # Set git config for commits
            subprocess.run(["git", "config", "user.name", "Disgram Bot"], 
                          cwd=".", capture_output=True, text=True, check=True)
            subprocess.run(["git", "config", "user.email", "disgram@bot.local"], 
                          cwd=".", capture_output=True, text=True, check=True)
            
            # Configure Git to use token-based authentication
            # Use the token as username with empty password (GitHub's recommended approach)
            subprocess.run([
                "git", "config", "credential.helper", 
                f"!f() {{ echo \"username={self.github_token}\"; echo \"password=\"; }}; f"
            ], cwd=".", capture_output=True, text=True, check=True)
            
            # Ensure remote URL is clean HTTPS without embedded credentials
            result = subprocess.run(["git", "remote", "get-url", "origin"], 
                                   cwd=".", capture_output=True, text=True, check=True)
            current_url = result.stdout.strip()
            
            # Clean up URL if it has embedded credentials
            if "@github.com/" in current_url:
                # Extract just the repo path and reconstruct clean URL
                repo_part = current_url.split("@github.com/")[1]
                clean_url = f"https://github.com/{repo_part}"
                subprocess.run(["git", "remote", "set-url", "origin", clean_url], 
                              cwd=".", capture_output=True, text=True, check=True)
                logger.info(f"Git authentication configured for repository: {repo_part}")
            elif current_url.startswith("https://github.com/"):
                repo_path = current_url.replace("https://github.com/", "")
                logger.info(f"Git authentication configured for repository: {repo_path}")
            else:
                logger.warning(f"Unexpected remote URL format: {sanitize_url_for_logging(current_url)}")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Error configuring git authentication: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in git configuration: {e}")
    
    def _get_last_commit_time(self) -> float:
        """Get the timestamp of the last auto-commit to determine cooldown"""
        try:
            # Get the last commit that was an auto-commit (our commits start with "Auto-commit:")
            result = subprocess.run([
                "git", "log", "--grep=^Auto-commit:", "--format=%ct", "-1"
            ], cwd=".", capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                last_auto_commit_time = float(result.stdout.strip())
                logger.debug(f"Found last auto-commit at {datetime.fromtimestamp(last_auto_commit_time)}")
                return last_auto_commit_time
            else:
                # No auto-commits found, check for any recent commits in the last 24 hours
                one_day_ago = int(time.time()) - 86400
                result = subprocess.run([
                    "git", "log", f"--since={one_day_ago}", "--format=%ct", "-1"
                ], cwd=".", capture_output=True, text=True)
                
                if result.returncode == 0 and result.stdout.strip():
                    recent_commit_time = float(result.stdout.strip())
                    logger.debug(f"Found recent commit at {datetime.fromtimestamp(recent_commit_time)}")
                    return recent_commit_time
                else:
                    logger.debug("No recent commits found, using current time minus interval")
                    return time.time() - self.commit_interval
                    
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.debug(f"Could not determine last commit time: {e}")
            return time.time() - self.commit_interval  # Safe fallback
        except Exception as e:
            logger.debug(f"Unexpected error getting last commit time: {e}")
            return time.time() - self.commit_interval  # Safe fallback
    
    def _sync_with_remote(self) -> bool:
        """Safely sync with remote repository, handling branch tracking issues"""
        try:
            # Get current branch name
            branch_result = subprocess.run(["git", "branch", "--show-current"], 
                                         cwd=".", capture_output=True, text=True)
            if branch_result.returncode != 0:
                logger.warning("Could not determine current branch")
                return False
                
            current_branch = branch_result.stdout.strip()
            
            # First try to fetch the remote branch
            fetch_result = subprocess.run(["git", "fetch", "origin", current_branch], 
                                        cwd=".", capture_output=True, text=True)
            if fetch_result.returncode != 0:
                logger.debug(f"Fetch failed: {sanitize_url_for_logging(fetch_result.stderr)}")
                return False
            
            # Check if we have upstream tracking
            upstream_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", f"{current_branch}@{{upstream}}"], 
                                           cwd=".", capture_output=True, text=True)
            
            if upstream_result.returncode != 0:
                # No upstream set, try to set it
                logger.debug(f"Setting upstream tracking for branch {current_branch}")
                subprocess.run(["git", "branch", "--set-upstream-to", f"origin/{current_branch}", current_branch], 
                              cwd=".", capture_output=True, text=True)
            
            # Now try to pull with explicit branch to avoid ambiguity
            pull_result = subprocess.run(["git", "pull", "origin", current_branch], 
                                       cwd=".", capture_output=True, text=True)
            
            if pull_result.returncode == 0:
                logger.debug("Successfully synced with remote")
                return True
            else:
                logger.debug(f"Pull failed: {sanitize_url_for_logging(pull_result.stderr)}")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.debug(f"Sync failed: {e}")
            return False
        except Exception as e:
            logger.debug(f"Unexpected error during sync: {e}")
            return False
    
    def _push_changes(self) -> bool:
        """Push changes to remote repository with proper error handling"""
        try:
            # Get current branch name
            branch_result = subprocess.run(["git", "branch", "--show-current"], 
                                         cwd=".", capture_output=True, text=True)
            if branch_result.returncode != 0:
                logger.error("Could not determine current branch for push")
                return False
                
            current_branch = branch_result.stdout.strip()
            
            # Try to push with explicit branch first
            result = subprocess.run(["git", "push", "origin", current_branch], 
                                   cwd=".", capture_output=True, text=True)
            
            if result.returncode == 0:
                return True
            
            # If push fails, try to handle common issues
            stderr = result.stderr
            
            if "has no upstream branch" in stderr:
                logger.info("Setting upstream branch and pushing...")
                result = subprocess.run(["git", "push", "--set-upstream", "origin", current_branch], 
                                      cwd=".", capture_output=True, text=True)
                return result.returncode == 0
            
            elif "non-fast-forward" in stderr or "rejected" in stderr:
                logger.warning("Push rejected, trying to sync and retry...")
                # Try to sync again and retry push
                if self._sync_with_remote():
                    result = subprocess.run(["git", "push", "origin", current_branch], 
                                          cwd=".", capture_output=True, text=True)
                    return result.returncode == 0
                else:
                    # As last resort, force push (only for log files, should be safe)
                    logger.warning("Using force push as last resort for log files...")
                    result = subprocess.run(["git", "push", "--force-with-lease", "origin", current_branch], 
                                          cwd=".", capture_output=True, text=True)
                    return result.returncode == 0
            
            logger.error(f"Push failed: {sanitize_url_for_logging(stderr)}")
            return False
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Push error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during push: {e}")
            return False
    
    def commit_changes(self, force: bool = False) -> bool:
        """Commit and push log file changes to repository"""
        if not self.github_token:
            logger.debug("No GitHub token configured - skipping commit")
            return False
        
        # Safety check: respect cooldown period unless this is a force commit
        if not force:
            current_time = time.time()
            time_since_last_commit = current_time - self.last_commit_time
            
            # Use different cooldown logic based on commit mode  
            if self.commit_mode == "scheduled":
                # For scheduled mode, ensure at least 55 minutes between commits
                min_cooldown = 3300  # 55 minutes
                if time_since_last_commit < min_cooldown:
                    remaining_cooldown = min_cooldown - time_since_last_commit
                    logger.debug(f"Scheduled commit cooldown active: {remaining_cooldown//60:.1f} minutes remaining")
                    return False
            else:
                # For interval mode, use the configured interval
                if time_since_last_commit < self.commit_interval:
                    remaining_cooldown = self.commit_interval - time_since_last_commit
                    logger.debug(f"Interval commit cooldown active: {remaining_cooldown//60:.1f} minutes remaining")
                    return False
            
        try:
            # Define the specific log files we want to track
            log_files = ["Disgram.log", "app.log"]
            changed_log_files = []
            
            # Check which log files have actually changed
            for log_file in log_files:
                if os.path.exists(log_file):
                    # Check if file has changes using git status
                    result = subprocess.run(["git", "status", "--porcelain", log_file], 
                                          cwd=".", capture_output=True, text=True)
                    if result.stdout.strip():  # File has changes
                        changed_log_files.append(log_file)
            
            if not changed_log_files:
                logger.debug("No log file changes to commit")
                return True  # No changes is still success
            
            # Try to sync with remote before committing
            logger.debug("Syncing with remote repository...")
            sync_success = self._sync_with_remote()
            if not sync_success:
                logger.warning("Could not sync with remote, continuing with local commit")
            
            logger.info(f"Log files to be committed: {', '.join(changed_log_files)}")
            
            # Add only the specific log files
            for log_file in changed_log_files:
                subprocess.run(["git", "add", log_file], 
                              cwd=".", capture_output=True, text=True, check=True)
            
            # Create commit with timestamp and log file list
            timestamp = datetime.now().isoformat()
            if len(changed_log_files) == 1:
                commit_message = f"Auto-commit: Update {changed_log_files[0]} - {timestamp}"
            else:
                commit_message = f"Auto-commit: Update log files ({', '.join(changed_log_files)}) - {timestamp}"
            
            subprocess.run(["git", "commit", "-m", commit_message], 
                          cwd=".", capture_output=True, text=True, check=True)
            
            # Push to repository if token is configured
            if self.github_token:
                push_success = self._push_changes()
                if push_success:
                    total_size = sum(os.path.getsize(f) for f in log_files if os.path.exists(f))
                    logger.info(f"Successfully committed and pushed {len(changed_log_files)} log file(s) to repository (total size: {total_size} bytes)")
                    self.last_commit_time = time.time()
                    return True
                else:
                    logger.error("Commit successful but push failed")
                    return False
            else:
                logger.info(f"Files committed locally (no GitHub token configured for push)")
                self.last_commit_time = time.time()
                return True
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Error committing files: {e}")
            if e.stderr:
                logger.error(f"Git error output: {sanitize_url_for_logging(e.stderr)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during commit: {e}")
            return False
    
    def pull_latest_log(self) -> bool:
        """Pull the latest version of the repository to get updated log file"""
        try:
            # Get current branch name
            branch_result = subprocess.run(["git", "branch", "--show-current"], 
                                         cwd=".", capture_output=True, text=True)
            if branch_result.returncode != 0:
                logger.error("Could not determine current branch")
                return False
                
            current_branch = branch_result.stdout.strip()
            
            # First, stash any local changes to avoid conflicts
            subprocess.run(["git", "stash", "push", "-m", "Auto-stash before pull"], 
                          cwd=".", capture_output=True, text=True)
            
            # Try to pull with explicit branch
            result = subprocess.run(["git", "pull", "origin", current_branch], 
                                   cwd=".", capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("Successfully pulled latest repository state")
                return True
            else:
                logger.warning(f"Pull failed: {sanitize_url_for_logging(result.stderr)}")
                return False
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error pulling repository: {e}")
            if e.stderr:
                logger.error(f"Git error output: {sanitize_url_for_logging(e.stderr)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during pull: {e}")
            return False
    
    def _background_commit(self):
        """Background thread to periodically commit log file using interval or scheduled mode"""
        while True:
            try:
                time.sleep(60)  # Check every minute
                
                current_time = time.time()
                should_commit = False
                commit_reason = ""
                
                if self.commit_mode == "scheduled":
                    # Scheduled mode: commit at specific UTC times
                    if self._is_scheduled_time():
                        # Check if we haven't committed recently to avoid spam
                        time_since_last_commit = current_time - self.last_commit_time
                        if time_since_last_commit >= 3300:  # At least 55 minutes since last commit
                            should_commit = True
                            commit_reason = "scheduled"
                        else:
                            from datetime import datetime, timezone
                            now_utc = datetime.now(timezone.utc)
                            logger.info(f"Scheduled commit time ({now_utc.hour:02d}:00 UTC) but recent commit detected, skipping")
                    
                    # Log next scheduled time occasionally
                    if int(current_time) % 600 == 0:  # Every 10 minutes
                        next_time = self._get_next_scheduled_time()
                        if next_time:
                            from datetime import datetime, timezone
                            next_dt = datetime.fromtimestamp(next_time, timezone.utc)
                            logger.debug(f"Next scheduled commit: {next_dt.strftime('%H:%M UTC')}")
                
                else:
                    # Interval mode: commit after fixed intervals
                    time_since_last_commit = current_time - self.last_commit_time
                    if time_since_last_commit >= self.commit_interval:
                        should_commit = True
                        commit_reason = f"interval ({time_since_last_commit//60:.1f} minutes)"
                    else:
                        # Log the countdown occasionally (every 10 minutes)  
                        if int(time_since_last_commit) % 600 == 0:
                            time_until_next = self.commit_interval - time_since_last_commit
                            logger.debug(f"Next interval commit in {time_until_next//60:.1f} minutes")
                
                # Execute commit if conditions are met
                if should_commit:
                    with self.commit_lock:
                        # Check if there are specific log file changes to commit
                        log_files = ["Disgram.log", "app.log"]
                        has_log_changes = False
                        
                        for log_file in log_files:
                            if os.path.exists(log_file):
                                result = subprocess.run(["git", "status", "--porcelain", log_file], 
                                                       cwd=".", capture_output=True, text=True)
                                if result.returncode == 0 and result.stdout.strip():
                                    has_log_changes = True
                                    break
                        
                        if has_log_changes:
                            logger.info(f"Background commit triggered by {commit_reason}, committing log changes...")
                            success = self.commit_changes()
                            if success:
                                logger.info(f"Background commit completed successfully ({commit_reason})")
                            else:
                                logger.warning(f"Background commit failed ({commit_reason})")
                        else:
                            logger.debug(f"Background commit: No log file changes detected, skipping {commit_reason} commit")
                        
            except Exception as e:
                logger.error(f"Background commit error: {e}")
    
    def force_commit(self) -> bool:
        """Force immediate commit to repository, bypassing cooldown"""
        with self.commit_lock:
            logger.info("Force commit requested, bypassing cooldown period")
            return self.commit_changes(force=True)
    
    def get_commit_status(self) -> dict:
        """Get commit status for health monitoring"""
        try:
            # Get last commit info
            result = subprocess.run([
                "git", "log", "-1", "--format=%H|%ci|%s", "--", self.local_log_path
            ], cwd=".", capture_output=True, text=True, check=True)
            
            if result.stdout.strip():
                parts = result.stdout.strip().split("|", 2)
                last_commit_hash = parts[0][:8]  # Short hash
                last_commit_date = parts[1]
                last_commit_message = parts[2] if len(parts) > 2 else "No message"
            else:
                last_commit_hash = "none"
                last_commit_date = "never"
                last_commit_message = "No commits found"
            
            current_time = time.time()
            time_since_commit = current_time - self.last_commit_time
            
            # Calculate next commit timing based on mode
            if self.commit_mode == "scheduled":
                next_scheduled = self._get_next_scheduled_time()
                next_commit_info = {
                    "mode": "scheduled",
                    "schedule": self._get_schedule_description(),
                    "next_commit_timestamp": next_scheduled,
                    "next_commit_in_seconds": max(0, next_scheduled - current_time) if next_scheduled else None
                }
                
                # Add current UTC time info
                from datetime import datetime, timezone
                now_utc = datetime.now(timezone.utc)
                next_commit_info["current_utc"] = now_utc.strftime("%H:%M UTC")
                if next_scheduled:
                    next_dt = datetime.fromtimestamp(next_scheduled, timezone.utc)
                    next_commit_info["next_commit_utc"] = next_dt.strftime("%H:%M UTC")
            else:
                next_commit_info = {
                    "mode": "interval",
                    "interval_minutes": self.commit_interval // 60,
                    "next_commit_in_seconds": max(0, self.commit_interval - time_since_commit)
                }
            
            return {
                "git_available": True,
                "commit_mode": self.commit_mode,
                "last_commit_time": self.last_commit_time,
                "time_since_commit_seconds": time_since_commit,
                "time_since_commit_minutes": time_since_commit // 60,
                "last_commit_hash": last_commit_hash,
                "last_commit_date": last_commit_date,
                "last_commit_message": last_commit_message,
                "github_token_configured": self.github_token is not None,
                **next_commit_info
            }
            
        except Exception as e:
            return {
                "git_available": False,
                "error": str(e),
                "commit_mode": self.commit_mode,
                "last_commit_time": self.last_commit_time,
                "github_token_configured": self.github_token is not None
            }

# Global instance
git_log_manager: Optional[GitLogManager] = None

def initialize_git_manager():
    """Initialize Git manager if GitHub token is available"""
    global git_log_manager
    
    github_token = os.getenv("GITHUB_TOKEN")
    commit_interval = int(os.getenv("LOG_COMMIT_INTERVAL", "2700"))  # Default 45 minutes
    
    try:
        git_log_manager = GitLogManager(github_token, commit_interval)
        logger.info(f"Git log manager initialized successfully (commit interval: {commit_interval//60} minutes)")
        
        # Pull latest version on startup
        if git_log_manager.pull_latest_log():
            logger.info("Repository updated with latest changes")
            
    except Exception as e:
        logger.error(f"Failed to initialize Git manager: {e}")
        git_log_manager = None