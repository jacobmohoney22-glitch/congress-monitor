from __future__ import annotations

import requests

TELEGRAM_LIMIT = 4096
SEPARATOR = "\n\n- - - - - - - - - -\n\n"


def pack_messages(texts: list[str], limit: int = 3500) -> list[list[int]]:
    """Group whole alerts into as few Telegram messages as fit (an alert is never split)."""
    groups, cur, size = [], [], 0
    for i, t in enumerate(texts):
        add = len(t) + len(SEPARATOR)
        if cur and size + add > limit:
            groups.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += add
    if cur:
        groups.append(cur)
    return groups


def split_message(text: str, limit: int = TELEGRAM_LIMIT - 100) -> list[str]:
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        cut = limit if cut <= 0 else cut
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    chunks.append(text)
    return chunks


class ConsoleNotifier:
    def send(self, text: str) -> bool:
        print("---- ALERT ----\n" + text + "\n")
        return True


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, session: requests.Session | None = None):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id
        self.session = session or requests.Session()

    def send(self, text: str) -> bool:
        ok = True
        for chunk in split_message(text):
            try:
                r = self.session.post(self.url, timeout=20, json={
                    "chat_id": self.chat_id, "text": chunk, "parse_mode": "HTML",
                    "disable_web_page_preview": True})
                if r.status_code != 200:
                    ok = False
                    print(f"telegram send failed: HTTP {r.status_code} {r.text[:200]}")
            except requests.RequestException as e:
                ok = False
                print(f"telegram send failed: {type(e).__name__}")   # never print the URL (token)
        return ok
