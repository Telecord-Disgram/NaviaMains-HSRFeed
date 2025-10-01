"""
Discord Rate Limiter Module

Implements Discord's rate limiting requirements according to their documentation:
https://discord.com/developers/docs/topics/rate-limits

This module handles:
- Per-route rate limits with bucket tracking
- Global rate limits (50 requests/second for bots)
- Proper retry-after handling for 429 responses
- Rate limit header parsing and tracking
- Automatic backoff and retry logic
"""

import time
import threading
import requests
import json
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging


@dataclass
class RateLimitBucket:
    """Represents a Discord rate limit bucket"""
    limit: int = 0
    remaining: int = 0
    reset_time: float = 0.0
    reset_after: float = 0.0
    bucket_id: str = ""
    last_request_time: float = 0.0


class DiscordRateLimiter:
    """
    Discord-compliant rate limiter that handles:
    - Per-route rate limits with bucket tracking
    - Global rate limits (50 requests/second)
    - Proper 429 retry handling
    - Rate limit header parsing
    """
    
    def __init__(self):
        self.buckets: Dict[str, RateLimitBucket] = {}
        self.global_rate_limit_reset = 0.0
        self.global_requests_made = 0
        self.global_window_start = time.time()
        self.lock = threading.RLock()
        
        # Global rate limit: 50 requests per second
        self.global_limit = 50
        self.global_window_size = 1.0
        
        # Track invalid requests to avoid Cloudflare bans
        self.invalid_requests_count = 0
        self.invalid_requests_window_start = time.time()
        self.max_invalid_requests = 9000  # Stay below 10,000 per 10 minutes
        self.invalid_requests_window = 600
        
        self.logger = logging.getLogger(__name__)
    
    def _get_bucket_key(self, url: str, method: str = "POST") -> str:
        """
        Generate a bucket key for rate limiting.
        For webhooks, we use the webhook URL as the bucket key.
        """
        if "/webhooks/" in url:
            base_url = url.split("?")[0]
            parts = base_url.split("/webhooks/")[1].split("/")
            webhook_id = parts[0]
            if len(parts) > 1 and parts[1]:
                # Include token in bucket key for webhook+token endpoints
                return f"{method}:webhook:{webhook_id}:{parts[1][:8]}"
            else:
                return f"{method}:webhook:{webhook_id}"
        
        return f"{method}:{url}"
    
    def _update_bucket_from_headers(self, bucket_key: str, headers: Dict[str, str]) -> RateLimitBucket:
        """Update bucket information from Discord response headers"""
        with self.lock:
            bucket = self.buckets.get(bucket_key, RateLimitBucket())
            
            if "X-RateLimit-Limit" in headers:
                bucket.limit = int(headers["X-RateLimit-Limit"])
            
            if "X-RateLimit-Remaining" in headers:
                bucket.remaining = int(headers["X-RateLimit-Remaining"])
            
            if "X-RateLimit-Reset" in headers:
                bucket.reset_time = float(headers["X-RateLimit-Reset"])
            
            if "X-RateLimit-Reset-After" in headers:
                bucket.reset_after = float(headers["X-RateLimit-Reset-After"])
            
            if "X-RateLimit-Bucket" in headers:
                bucket.bucket_id = headers["X-RateLimit-Bucket"]
            
            bucket.last_request_time = time.time()
            self.buckets[bucket_key] = bucket
            
            return bucket
    
    def _check_global_rate_limit(self) -> Optional[float]:
        """
        Check global rate limit (50 requests/second).
        Returns wait time in seconds if rate limited, None otherwise.
        """
        with self.lock:
            current_time = time.time()
            
            # Reset window if needed
            if current_time - self.global_window_start >= self.global_window_size:
                self.global_requests_made = 0
                self.global_window_start = current_time
            
            # Check if we're at the limit
            if self.global_requests_made >= self.global_limit:
                wait_time = self.global_window_size - (current_time - self.global_window_start)
                if wait_time > 0:
                    return wait_time
                else:
                    # Window expired, reset
                    self.global_requests_made = 0
                    self.global_window_start = current_time
            
            return None
    
    def _check_bucket_rate_limit(self, bucket_key: str) -> Optional[float]:
        """
        Check bucket-specific rate limit.
        Returns wait time in seconds if rate limited, None otherwise.
        """
        with self.lock:
            bucket = self.buckets.get(bucket_key)
            if not bucket:
                return None
            
            current_time = time.time()
            
            # Check if bucket has reset
            if current_time >= bucket.reset_time:
                bucket.remaining = bucket.limit
                return None
            
            if bucket.remaining <= 0:
                wait_time = bucket.reset_time - current_time
                return max(wait_time, 0)
            
            return None
    
    def _increment_global_counter(self):
        with self.lock:
            self.global_requests_made += 1
    
    def _decrement_bucket_remaining(self, bucket_key: str):
        with self.lock:
            bucket = self.buckets.get(bucket_key)
            if bucket and bucket.remaining > 0:
                bucket.remaining -= 1
    
    def _handle_invalid_request(self, status_code: int):
        """Track invalid requests to avoid Cloudflare bans"""
        if status_code in [401, 403, 429]:
            with self.lock:
                current_time = time.time()
                
                # Reset window if needed
                if current_time - self.invalid_requests_window_start >= self.invalid_requests_window:
                    self.invalid_requests_count = 0
                    self.invalid_requests_window_start = current_time
                
                self.invalid_requests_count += 1
                
                # Log warning if approaching limit
                if self.invalid_requests_count > self.max_invalid_requests * 0.8:
                    self.logger.warning(
                        f"High invalid request count: {self.invalid_requests_count}/{self.max_invalid_requests}. "
                        f"Risk of Cloudflare ban."
                    )
    
    def wait_for_rate_limit(self, url: str, method: str = "POST") -> bool:
        """
        Wait for rate limits before making a request.
        Returns True if request can proceed, False if should be aborted.
        """
        bucket_key = self._get_bucket_key(url, method)
        
        global_wait = self._check_global_rate_limit()
        if global_wait:
            self.logger.info(f"Global rate limit hit, waiting {global_wait:.2f} seconds")
            time.sleep(global_wait)
        
        bucket_wait = self._check_bucket_rate_limit(bucket_key)
        if bucket_wait:
            self.logger.info(f"Bucket rate limit hit for {bucket_key}, waiting {bucket_wait:.2f} seconds")
            time.sleep(bucket_wait)
        
        return True
    
    def handle_response(self, response: requests.Response, url: str, method: str = "POST") -> Tuple[bool, Optional[float]]:
        """
        Handle Discord API response and update rate limit tracking.
        
        Returns:
            (should_retry, wait_time): 
            - should_retry: True if request should be retried
            - wait_time: Time to wait before retry (None if no retry needed)
        """
        bucket_key = self._get_bucket_key(url, method)
        
        # Update rate limit tracking from headers
        self._update_bucket_from_headers(bucket_key, dict(response.headers))
        
        # Track request counts
        self._increment_global_counter()
        
        if response.status_code == 429:
            self._handle_invalid_request(429)
            
            try:
                retry_data = response.json()
                retry_after = retry_data.get("retry_after", 1.0)
                is_global = retry_data.get("global", False)
                
                if is_global:
                    self.logger.warning(f"Global rate limit exceeded, waiting {retry_after} seconds")
                    with self.lock:
                        self.global_rate_limit_reset = time.time() + retry_after
                else:
                    self.logger.warning(f"Bucket rate limit exceeded for {bucket_key}, waiting {retry_after} seconds")
                
                return True, retry_after
                
            except (json.JSONDecodeError, KeyError):
                retry_after = float(response.headers.get("Retry-After", 1.0))
                self.logger.warning(f"Rate limit exceeded, waiting {retry_after} seconds (from headers)")
                return True, retry_after
        
        elif response.status_code in [401, 403]:
            self._handle_invalid_request(response.status_code)
            return False, None
        
        elif response.status_code == 404:
            self.logger.error("Webhook not found (404) - check webhook URL")
            return False, None
        
        elif 500 <= response.status_code < 600:
            # Server error - retry with exponential backoff
            return True, min(2.0 ** (response.status_code - 500), 60.0)
        
        else:
            # Success or other status - decrement bucket counter
            if response.status_code < 400:
                self._decrement_bucket_remaining(bucket_key)
            
            return False, None
    
    def make_request_with_rate_limiting(self, 
                                       url: str, 
                                       method: str = "POST", 
                                       max_retries: int = 5,
                                       **kwargs) -> Optional[requests.Response]:
        """
        Make a rate-limited request to Discord API.
        
        Args:
            url: Discord API URL
            method: HTTP method
            max_retries: Maximum number of retry attempts
            **kwargs: Additional arguments for requests
        
        Returns:
            Response object if successful, None if failed permanently
        """
        for attempt in range(max_retries + 1):
            if not self.wait_for_rate_limit(url, method):
                return None
            
            try:
                response = requests.request(method, url, timeout=30, **kwargs)
                
                should_retry, wait_time = self.handle_response(response, url, method)
                
                if not should_retry:
                    return response
                
                if attempt < max_retries and wait_time:
                    self.logger.info(f"Retrying request in {wait_time:.2f} seconds (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                
                if attempt >= max_retries:
                    self.logger.error(f"Max retries ({max_retries}) exceeded for {url}")
                    return response
                    
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Request exception on attempt {attempt + 1}: {e}")
                if attempt < max_retries:
                    wait_time = min(2.0 ** attempt, 60.0)
                    time.sleep(wait_time)
                    continue
                else:
                    return None
        
        return None
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status for monitoring"""
        with self.lock:
            current_time = time.time()
            return {
                "global": {
                    "requests_made": self.global_requests_made,
                    "limit": self.global_limit,
                    "window_remaining": max(0, self.global_window_size - (current_time - self.global_window_start)),
                    "reset_time": self.global_rate_limit_reset if self.global_rate_limit_reset > current_time else None
                },
                "buckets": {
                    bucket_key: {
                        "limit": bucket.limit,
                        "remaining": bucket.remaining,
                        "reset_time": bucket.reset_time,
                        "reset_after": max(0, bucket.reset_time - current_time) if bucket.reset_time > current_time else 0
                    }
                    for bucket_key, bucket in self.buckets.items()
                },
                "invalid_requests": {
                    "count": self.invalid_requests_count,
                    "limit": self.max_invalid_requests,
                    "window_remaining": max(0, self.invalid_requests_window - (current_time - self.invalid_requests_window_start))
                }
            }

discord_rate_limiter = DiscordRateLimiter()