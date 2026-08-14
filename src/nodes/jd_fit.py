"""jd_fit node: asks JD-gap-sourced questions. See _content_node.py for
the shared implementation."""

from src.graph import InterviewState
from src.nodes._content_node import content_node

NODE_NAME = "jd_fit"
SOURCE = "jd"


async def run(state: InterviewState) -> dict:
    return await content_node(state, node_name=NODE_NAME, source=SOURCE)
