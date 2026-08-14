"""resume_probe node: asks resume-sourced questions. See _content_node.py
for the shared implementation."""

from src.graph import InterviewState
from src.nodes._content_node import content_node

NODE_NAME = "resume_probe"
SOURCE = "resume"


async def run(state: InterviewState) -> dict:
    return await content_node(state, node_name=NODE_NAME, source=SOURCE)
