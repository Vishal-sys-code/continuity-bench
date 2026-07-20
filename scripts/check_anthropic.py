import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

try:
    message = client.messages.create(
        model="claude-2.1",
        max_tokens=10,
        messages=[
            {"role": "user", "content": "Hello"}
        ]
    )
    print("API Key is VALID and ACTIVE. Request succeeded.")
except anthropic.APIStatusError as e:
    print(f"API Status Error: {e.status_code}")
    print(f"Error Message: {e.message}")
    print(f"Error Body: {e.response.json()}")
except Exception as e:
    print(f"Unexpected error: {e}")
