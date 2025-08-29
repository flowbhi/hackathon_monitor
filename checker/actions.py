import requests, json

def http_post(url, payload=None):
    r = requests.post(url, json=payload or {})
    return {"status_code": r.status_code, "text": (r.text[:200] if r.text else "")}

ACTIONS = {
    "http_post": http_post
}
