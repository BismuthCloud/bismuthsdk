import logging
import os
import pathlib
import sys
from bismuthsdk import BismuthClient

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("bismuthsdk").setLevel(logging.DEBUG)
    logging.getLogger("git").setLevel(logging.DEBUG)

    repo_dir = pathlib.Path(sys.argv[1])

    api = BismuthClient(api_key=os.environ["BISMUTH_API_KEY"])
    project = api.load_project(repo_dir)
    branch = project.get_branch("main")

    res = branch.review_changes(
        message="add interpolate function",
        changed_files={
            "wx_explore/analysis/helpers.py": (
                repo_dir / "wx_explore/analysis/helpers.py"
            ).read_text()
        },
    )
    print(res.message)

    for bug in res.bugs:
        print(bug.file, bug.start_line)
        print(bug.description)
        print(bug.suggested_fix)
