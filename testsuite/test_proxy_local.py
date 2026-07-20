import sys
from pathlib import Path
sys.path.insert(0, str(Path(r"d:\Github\continuity-bench")))
from systems.baseline.proxy import BaselineProxy

class DummyProvider:
    def chat(self, *args, **kwargs):
        class Res:
            text = "hello"
            latency_ms = 100
            model = "dummy"
        return Res()
    
class DummyFault:
    def get_failure_event(self, *args, **kwargs):
        return None

proxy = BaselineProxy()
proxy.primary = DummyProvider()
proxy.injector = DummyFault()
proxy.fallback_names = []

try:
    proxy.handle_chat_completion(messages=[{"role":"user","content":"hi"}])
    print("SUCCESS!")
except Exception as e:
    import traceback
    traceback.print_exc()
