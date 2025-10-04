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
        self.commit_interval = commit_interval  # 45 minutes in seconds
        self.local_log_path = "Disgram.log"
        self.last_commit_time = 0
        self.commit_lock = threading.Lock()
        
        # Configure git if token is provided
        if self.github_token:
            self._configure_git_auth()
        
        # Start background commit thread
        self.commit_thread = threading.Thread(target=self._background_commit, daemon=True)
        self.commit_thread.start()
        
        logger.info(f"GitLogManager initialized - commit interval: {commit_interval//60} minutes")
    
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
    
    def commit_changes(self) -> bool:
        """Commit and push log file changes to repository"""
        if not self.github_token:
            logger.debug("No GitHub token configured - skipping commit")
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
        """Background thread to periodically commit log file"""
        while True:
            try:
                time.sleep(60)  # Check every minute
                
                current_time = time.time()
                if (current_time - self.last_commit_time) >= self.commit_interval:
                    with self.commit_lock:
                        # Check if there are any changes to commit
                        result = subprocess.run(["git", "status", "--porcelain"], 
                                               cwd=".", capture_output=True, text=True)
                        if result.returncode == 0 and result.stdout.strip():
                            logger.info(f"Background commit: Committing changed files to repository...")
                            self.commit_changes()
                        
            except Exception as e:
                logger.error(f"Background commit error: {e}")
    
    def force_commit(self) -> bool:
        """Force immediate commit to repository"""
        with self.commit_lock:
            return self.commit_changes()
    
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
            
            return {
                "git_available": True,
                "last_commit_time": self.last_commit_time,
                "time_since_commit": time.time() - self.last_commit_time,
                "next_commit_in": max(0, self.commit_interval - (time.time() - self.last_commit_time)),
                "last_commit_hash": last_commit_hash,
                "last_commit_date": last_commit_date,
                "last_commit_message": last_commit_message,
                "github_token_configured": self.github_token is not None
            }
            
        except Exception as e:
            return {
                "git_available": False,
                "error": str(e),
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