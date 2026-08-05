import threading, time, urllib.request, json, asyncio
import sys
sys.path.insert(0, ".")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

events = []
def listen():
    req = urllib.request.Request("http://127.0.0.1:8777/api/stream")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        for raw in resp:
            text = raw.decode()
            if text.startswith("data:"):
                events.append(json.loads(text[5:].strip())["tasks"])
    except Exception as e:
        events.append(f"SSE-ERROR: {e}")

t = threading.Thread(target=listen)
t.daemon = True
t.start()
time.sleep(1)

async def main():
    async with stdio_client(StdioServerParameters(
        command=".venv/bin/python", args=["server/mcp_server.py"])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            await s.call_tool("record_task", {"task_id": "sse-live", "name": "SSE实时验证", "agent": "codex", "stage": "testing"})
            await s.call_tool("update_progress", {"task_id": "sse-live", "progress": 60})
            await s.call_tool("log_node", {"task_id": "sse-live", "node_type": "milestone", "message": "实时推送链路验证"})
    time.sleep(2)
    if events and isinstance(events[0], list):
        seq = [f"{e[0]['status']}({e[0]['progress']}%)" for e in events if e]
        print("SSE 收到推送序列:", seq)
    else:
        print("events:", events)

asyncio.run(main())