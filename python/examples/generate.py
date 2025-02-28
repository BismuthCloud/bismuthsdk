import logging
import os
import pathlib
import subprocess
from bismuthsdk import BismuthClient, Location, apply_diff

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("bismuthsdk").setLevel(logging.DEBUG)
    logging.getLogger("git").setLevel(logging.DEBUG)

    example_dir = pathlib.Path("/tmp/bismuthsdk_example")
    if not example_dir.exists():
        example_dir.mkdir()
        subprocess.run(["git", "init"], cwd=example_dir)
        (example_dir / "test.py").write_text("print('Hello, world!')\n")
        subprocess.run(["git", "add", "."], cwd=example_dir)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=example_dir)

    api = BismuthClient(api_key=os.environ["BISMUTH_API_KEY"])
    project = api.load_project(example_dir)
    branch = project.get_branch("main")

    """
    Run the Bismuth agent on the given message, applying local_changes (file path -> content) to the repo before processing,
    and seeding the agent with the given start locations.

    If start_locations is not provided, the agent will attempt to find relevant locations in the codebase.
    If session is provided, the agent will create or continue from the previous session with the same name.

    Returns a unified diff that can be applied to the repo.
    """
    diff = branch.generate(
        "change test.py to say goodbye world",
        local_changes={},
        start_locations=None,
        session=None,
    )
    print(diff)
    if not apply_diff(example_dir, diff):
        print("Failed to apply patch?")

    commit_msg = branch.summarize_changes(diff)
    print(commit_msg)
