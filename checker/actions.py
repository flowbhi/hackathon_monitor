import requests, json
from .checks import expand_env

def http_post(url, payload=None):
    url = expand_env(url)
    r = requests.post(url, json=payload or {})
    return {"status_code": r.status_code, "text": (r.text[:200] if r.text else "")}

ACTIONS = {
    "http_post": http_post
}
