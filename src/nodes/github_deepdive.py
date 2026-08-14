"""github_deepdive node: asks GitHub-grounded questions (requirement #4,
>=3 must cite a real repo/file/commit -- enforced upstream in
question_planner.py, this node just asks what's in the plan). See
_content_node.py for the shared implementation."""

from src.graph import InterviewState
from src.nodes._content_node import content_node

NODE_NAME = "github_deepdive"
SOURCE = "github"


async def run(state: InterviewState) -> dict:
    return await content_node(state, node_name=NODE_NAME, source=SOURCE)
