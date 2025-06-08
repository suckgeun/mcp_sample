import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Dict, List, Optional, Any

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
)
from pydantic import BaseModel

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_NAME = "gpt-4.1"
TOOL_SEPARATOR = "__"  # unique separator to avoid name clashes
FINAL_TOOL_NAME = "final_answer"  # NEW: name of the structured-output tool

# ---------------------------------------------------------------------------
# Raw server configuration (edit this to add/remove MCP servers)
# ---------------------------------------------------------------------------

RAW_CONFIG: Dict[str, dict] = {
    "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
    "google_search": {
        "command": "uv",
        "args": ["--directory", "/path/to/your/project/servers/src", "run", "server_google_search.py"],
    },
}

# ---------------------------------------------------------------------------
# Typed configuration model
# ---------------------------------------------------------------------------


class MCPServer(BaseModel):
    name: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None
    session: Any = None  # filled in at runtime


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def mcp_tool_to_openai_tool(tool: Tool, server_name: str) -> dict:
    unique_name = f"{server_name}{TOOL_SEPARATOR}{tool.name}"
    return {
        "type": "function",
        "name": unique_name,
        "description": tool.description,
        "parameters": tool.inputSchema,
    }


async def init_servers(stack: AsyncExitStack, servers: Dict[str, MCPServer]) -> List[dict]:
    openai_tools: List[dict] = []

    for server in servers.values():
        read, write = await stack.enter_async_context(
            stdio_client(StdioServerParameters(command=server.command, args=server.args, env=server.env))
        )
        server.session = await stack.enter_async_context(ClientSession(read, write))
        await server.session.initialize()

        response = await server.session.list_tools()
        print(f"[{server.name}] available tools → {[t.name for t in response.tools]}")

        for t in response.tools:
            openai_tools.append(mcp_tool_to_openai_tool(t, server.name))

    return openai_tools


async def dispatch_tool_call(tool_call: ResponseFunctionToolCall, servers: Dict[str, MCPServer]) -> str:
    """Execute an MCP tool"""
    args = json.loads(tool_call.arguments)
    server_name, tool_name = tool_call.name.split(TOOL_SEPARATOR)
    session = servers[server_name].session
    result = await session.call_tool(name=tool_name, arguments=args)
    return str(result.content[0].text)


SYSTEM_PROMPT = f"""
あなたは日本のAI関連会社を分析する戦略コンサルタントです。与えられた会社名を調べてください。
必ず実情報から調べてください。フィクションや想像上の情報は書かないでください。
ターゲット業界など、推論が必要な情報は、確信がある場合のみ書いてください。
調べる対象は、必ず最近の3年以内のものに限定してください。


調べる時は、下記の手順を必ず守ってください。
1. 計画を立てる
2. 計画に従って、情報を調べる
3. 情報を基に現在分かっていることをまとめる
4. 追加計画を立てる（１に戻る）か、最終報告書としてまとめる。最終報告書には必ず {FINAL_TOOL_NAME}を含む


調べる項目としては、下記の内容は必ず含めてください。
- 会社名
- 提供するプロダクトやサービス名
- コアAIアルゴリズム：サービスに活用されているAIに関連する技術のみを記載する。（LLM, RAG, AIエージェント 等）。「AI」など、抽象度が高い単語は書かないでください。解析等の抽象語や、UI やデータ型や、業務分析, 公開情報解析, リアルタイムデータ解析などのアルゴリズムでは無い情報は書かない。
- AIタスク：サービスが実施するタスク（物体検知, 異常検知 など）。
- ターゲット課題：プロダクトやサービスが解決しようとする課題
- ターゲット業界：プロダクトやサービスがターゲットとする業界。明確に分かる特定可能な複数の業界を支援する場合は全て書いてください。
- 契約形態：プロダクトやサービスの契約形態（SaaS, API, オープンソース など）。受託開発の場合は、受託開発と書いてください。
- サービス詳細：プロダクトやサービスの詳細。具体的な機能や特徴を記載してください。

上記の内容をまとめて、会社調査報告書を作成してください。
どこで調べたか、出典元のURLを必ず書いてください。
"""


async def chat_loop(servers: Dict[str, MCPServer]) -> None:
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async with AsyncExitStack() as stack:
        tools = await init_servers(stack, servers)
        previous_id: Optional[str] = None

        user_text = await asyncio.to_thread(input, "You: ")

        call_kwargs = {
            "model": MODEL_NAME,
            "input": [
                {
                    "role": "developer",
                    "content": SYSTEM_PROMPT,
                },
                {"role": "user", "content": user_text},
            ],
            "tools": tools,
        }

        while True:
            print("\n\n\n\n" + "%" * 20)
            print("into the loop")
            print("%" * 20)
            if previous_id:
                call_kwargs["previous_response_id"] = previous_id
            print("input:", call_kwargs)

            response: Response = client.responses.create(**call_kwargs)

            output_msg = [obj for obj in response.output if isinstance(obj, ResponseOutputMessage)]
            output_func_call = [obj for obj in response.output if isinstance(obj, ResponseFunctionToolCall)]
            print("\n\n【First Response】")
            print(output_msg)
            print(output_func_call)
            print("-" * 20)

            for obj in output_msg:
                text = obj.content[0].text
                print(f"Assistant: {text}\n")
                print("-" * 20)
                if FINAL_TOOL_NAME in text:
                    print("&" * 50)
                    break  # already the final report!

            func_call_result = []
            for obj in output_func_call:
                print(f"\n### function call {obj.name} ###")
                print(f"\n### function param {obj.arguments} ###")
                tool_output = await dispatch_tool_call(obj, servers)
                print("\n$$$ function result $$$\n", tool_output, "\n")
                print("-" * 20)
                func_call_result.append(
                    {
                        "type": "function_call_output",
                        "call_id": obj.call_id,
                        "output": tool_output,
                    }
                )
            previous_id = response.id

            call_kwargs["input"] = func_call_result


# ---------------------------------------------------------------------------
# Entry helpers (unchanged)
# ---------------------------------------------------------------------------


def build_servers(raw: Dict[str, dict]) -> Dict[str, MCPServer]:
    return {name: MCPServer(name=name, **cfg) for name, cfg in raw.items()}


def main() -> None:
    servers = build_servers(RAW_CONFIG)
    asyncio.run(chat_loop(servers))


if __name__ == "__main__":
    main()
