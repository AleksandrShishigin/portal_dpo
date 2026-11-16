"""Validate provider-issued names before using one exact ALLOWED_HOSTS entry."""
import re

def valid_demo_host(host):
    return isinstance(host, str) and bool(re.fullmatch(
        r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.(?:trycloudflare\.com|ngrok-free\.dev|ngrok-free\.app|ngrok\.app|ngrok\.io)', host))
