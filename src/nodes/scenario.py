"""scenario node: catch-all for any remaining unasked questions regardless
of source, once resume/jd/github are each exhausted. See _content_node.py
for the shared implementation and ARCHITECTURE.md for why this doesn't
have its own dedicated question source in the schema."""

from src.graph import InterviewState
from src.nodes._content_node import content_node

NODE_NAME = "scenario"
SOURCE = "scenario"  # sentinel handled specially in _next_question()


async def run(state: InterviewState) -> dict:
    return await content_node(state, node_name=NODE_NAME, source=SOURCE)
