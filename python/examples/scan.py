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
    res = branch.scan(max_subsystems=1)

    print("Scanned subsystems:", ",".join(sub.name for sub in res.scanned_subsystems))
    print("Changesets:")
    for cs in res.changesets:
        print(cs.title)
        for commit in cs.commits:
            print(commit.message)
            print(commit.diff)
            print()
