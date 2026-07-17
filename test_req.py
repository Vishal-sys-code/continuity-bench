import urllib.request
import json
import urllib.error

data = {
    "messages": [{"role": "user", "content": "Hello"}],
    "conversation_id": "test-1",
    "turn_index": 0
}
req = urllib.request.Request(
    'http://127.0.0.1:8009/v1/chat/completions',
    data=json.dumps(data).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
try:
    res = urllib.request.urlopen(req)
    print(res.read().decode())
except urllib.error.URLError as e:
    print(f"Error: {e}")
