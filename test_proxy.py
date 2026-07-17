import sys, subprocess, os, time, json, requests
from dotenv import load_dotenv
load_dotenv()
env = os.environ.copy()
env['PYTHONUNBUFFERED'] = '1'
p = subprocess.Popen([sys.executable, '-m', 'systems.treatment.proxy', '--port', '8007'], env=env, stdout=open('proxy_out.log', 'w'), stderr=subprocess.STDOUT)
time.sleep(2)
try:
    with open('config/experiment_manifest.json', 'w') as f:
        json.dump([{'conversation_id': 'test-123', 'failure_turn': 0, 'assigned_fallback': 'anthropic'}], f)
    payload = {'messages': [{'role': 'user', 'content': 'Hello!'}], 'conversation_id': 'test-123', 'turn_index': 0}
    r = requests.post('http://127.0.0.1:8007/v1/chat/completions', json=payload)
    print(r.status_code)
    print(r.text)
except Exception as e:
    print("Error:", e)
finally:
    p.terminate()
