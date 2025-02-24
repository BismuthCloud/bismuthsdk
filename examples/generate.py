import logging
import os
import pathlib
import subprocess
from bismuthsdk import BismuthClient, Location

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("bismuthsdk").setLevel(logging.DEBUG)
    logging.getLogger("git").setLevel(logging.DEBUG)

    example_dir = pathlib.Path("/tmp/bismuthsdk_example")
    if not example_dir.exists():
        example_dir.mkdir()
        subprocess.run(["git", "init"], cwd=example_dir)
        (example_dir / "test.py").write_text("print('Hello, world!')")
        subprocess.run(["git", "add", "."], cwd=example_dir)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=example_dir)

    api = BismuthClient(api_key=os.environ["BISMUTH_API_KEY"])
    project = api.load_project(example_dir)
    branch = project.get_branch("main")
    diff = branch.generate(
        "change test.py to say goodbye world",
    )
    print(diff)

    commit_msg = branch.summarize_changes(diff)
    print(commit_msg)
