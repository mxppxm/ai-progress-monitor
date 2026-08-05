"""用 MCP client 接入看板 — 模拟 Clacky(我自己) 上报演示任务全流程"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    repo = "/Users/mico/clacky_workspace/ai-progress-monitor"
    params = StdioServerParameters(command=sys.executable, args=[repo + "/server/mcp_server.py"], cwd=repo)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            # MCP initialize handshake
            import mcp.types as types
            init = await session.initialize()
            print("MCP 连接成功:", init.serverInfo)

            # 1. 注册任务
            r = await session.call_tool("record_task", {"task_id":"clacky-demo","agent":"clacky","name":"把看板部署到可访问地址"})
            print("record_task:", r.content[0].text)
            print("---")
            # 2. 更新进度
            r = await session.call_tool("update_progress", {"task_id":"clacky-demo","progress":40,"stage":"coding","detail":"正在写静态页面"})
            print("update_progress 40%:", r.content[0].text[:90])
            print("---")
            # 3. 关键节点
            r = await session.call_tool("log_node", {"task_id":"clacky-demo","node_type":"milestone","message":"前端页面完成，SSE 已连通"})
            print("milestone::", r.content[0].text[:90])
            print("---")
            r = await session.call_tool("update_progress", {"task_id":"clacky-demo","progress":80,"stage":"deploying"})
            print("update 80%:", r.content[0].text[:90] if r.content else "ok")
            # 4. 最终成功
            r = await session.call_tool("log_node", {"task_id":"clacky-demo","node_type":"success","message":"看板上线，可实时查看"})
            print("success:", r.content[0].text[:110])

asyncio.run(main())