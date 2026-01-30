import os
import pathlib

import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator

GET_OBSERVATIONS_DATA_DIR = pathlib.Path(__file__).parent / "data/get_observations"
TEST_FILES = sorted(GET_OBSERVATIONS_DATA_DIR.glob("*.test.json"))


@pytest.mark.parametrize("path", TEST_FILES, ids=lambda p: p.name)
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DC_API_KEY"),
    reason="DC_API_KEY not set - eval tests require API access",
)
async def test_test_tool_agent(path: pathlib.Path) -> None:
    """Test the agent's basic ability via a session file."""
    await AgentEvaluator.evaluate(
        agent_module="evals.test_tool_agent.bootstrap",
        eval_dataset_file_path_or_dir=str(path),
        num_runs=2,
    )
