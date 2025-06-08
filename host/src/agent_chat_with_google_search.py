"""mcp_openai_tutorial.py

Tutorial script: calling external MCP tools (e.g. web‑fetch, Google search)
from an OpenAI model via function‑calling.

Run the script, then type questions.  The model will decide when to invoke a
function; tool outputs are automatically routed back to the model until it
responds with plain text.

Usage -> ``python mcp_openai_tutorial.py``
"""

import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Dict, List, Optional, Any

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.responses import Response, ResponseFunctionToolCall
from pydantic import BaseModel

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_NAME = "gpt-4.1"
TOOL_SEPARATOR = "__"  # unique separator to avoid name clashes across servers

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
    """Definition of a single MCP server instance."""

    name: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None
    session: Any = None  # filled in at runtime


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def mcp_tool_to_openai_tool(tool: Tool, server_name: str) -> dict:
    """Translate an MCP ``Tool`` into the schema expected by OpenAI."""
    unique_name = f"{server_name}{TOOL_SEPARATOR}{tool.name}"
    return {
        "type": "function",
        "name": unique_name,
        "description": tool.description,
        "parameters": tool.inputSchema,
    }


async def init_servers(stack: AsyncExitStack, servers: Dict[str, MCPServer]) -> List[dict]:
    """Launch all MCP servers and aggregate their tools in OpenAI format."""
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
    """Execute the requested MCP tool and return its string output."""
    args = json.loads(tool_call.arguments)
    server_name, tool_name = tool_call.name.split(TOOL_SEPARATOR)
    session = servers[server_name].session
    result = await session.call_tool(name=tool_name, arguments=args)
    return str(result.content[0].text)


async def chat_loop(servers: Dict[str, MCPServer]) -> None:
    """Interactive REPL: forwards user input to the model and handles tool calls."""
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async with AsyncExitStack() as stack:
        tools = await init_servers(stack, servers)
        previous_id: Optional[str] = None

        while True:
            user_text = await asyncio.to_thread(input, "You: ")
            if user_text.strip().lower() in {"exit", "quit"}:
                break

            call_kwargs = {
                "model": MODEL_NAME,
                "input": [{"role": "user", "content": user_text}],
                "tools": tools,
            }
            if previous_id:
                call_kwargs["previous_response_id"] = previous_id

            response: Response = client.responses.create(**call_kwargs)

            # Handle tool chains until we get plain‑text output
            while isinstance(response.output[0], ResponseFunctionToolCall):
                tool_call = response.output[0]
                tool_output = await dispatch_tool_call(tool_call, servers)

                response = client.responses.create(
                    model=MODEL_NAME,
                    previous_response_id=response.id,
                    input=[
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": tool_output,
                        }
                    ],
                    tools=tools,
                )

            assistant_message = response.output[0].content[0].text
            previous_id = response.id
            print(f"Assistant: {assistant_message}\n")


# ---------------------------------------------------------------------------
# Entry point helpers
# ---------------------------------------------------------------------------


def build_servers(raw: Dict[str, dict]) -> Dict[str, MCPServer]:
    """Convert the raw dict into typed ``MCPServer`` objects."""
    return {name: MCPServer(name=name, **cfg) for name, cfg in raw.items()}


def main() -> None:
    servers = build_servers(RAW_CONFIG)
    asyncio.run(chat_loop(servers))


if __name__ == "__main__":
    main()
