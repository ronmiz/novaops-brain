"""Milestone 1 check: a policy question returns a cited answer from the right document.

Goes through the MCP server (the real tool boundary), then one Converse call that
may answer ONLY from the retrieved hits and must cite them.

    python server/server.py                                   # terminal 1
    python scripts/ask.py E010 "Can I use my personal laptop for work?"   # terminal 2
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402

from novaops import config, llm  # noqa: E402

SYSTEM = (
    "You are the NovaOps internal assistant. Answer ONLY from the numbered sources. "
    "After every claim put its citation as [source § section]. If the sources do not "
    "answer the question, say what is missing. Where two sources disagree, the newer or "
    "more specific one governs — say which and why."
)


async def search(caller_id: str, question: str) -> list[dict]:
    async with streamablehttp_client(config.MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_documents", {"query": question, "caller_id": caller_id})
    if result.structuredContent and "result" in result.structuredContent:
        return result.structuredContent["result"]
    return [json.loads(block.text) for block in result.content]


def main() -> None:
    caller_id, question = sys.argv[1], " ".join(sys.argv[2:])
    hits = asyncio.run(search(caller_id, question))
    print(f"\nRetrieved for {caller_id}:")
    for h in hits:
        print(f"  {h['relevance']:.2f}  {h['source']} § {h['section']}")
    sources = "\n\n".join(
        f"[{h['source']} § {h['section']}] (dated {h['doc_date'] or 'n/a'})\n{h['text']}" for h in hits)
    answer = llm.converse(f"Sources:\n{sources}\n\nQuestion: {question}", system=SYSTEM)
    print(f"\nAnswer:\n{answer['text']}\n")


if __name__ == "__main__":
    main()
