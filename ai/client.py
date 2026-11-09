"""Claude API bağlantısı.

Anahtar yerelde .env dosyasından, bulutta (Streamlit Cloud) gizli ayarlardan okunur.
Anahtar asla koda yazılmaz.
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-5-5"


def get_client() -> Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY bulunamadi. .env dosyasini kontrol et.")
    return Anthropic(api_key=key)


if __name__ == "__main__":
    client = get_client()
    message = client.messages.create(
        model=MODEL,
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": "Tek cümleyle açıkla: GES proje finansmanında DSCR neden önemlidir?",
        }],
    )
    print(message.content[0].text)