import logging
import os
import pathlib
import sys
from git import Repo
from bismuthsdk import BismuthClient

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("bismuthsdk").setLevel(logging.DEBUG)
    logging.getLogger("git").setLevel(logging.DEBUG)

    repo_dir = pathlib.Path(sys.argv[1])
    repo = Repo(repo_dir)

    api = BismuthClient(api_key=os.environ["BISMUTH_API_KEY"])
    # try:
    #     api.get_project(repo_dir.name).delete()
    # except:
    #     pass
    project = api.load_project(repo_dir)
    branch = project.get_branch(repo.active_branch.name)
    res = branch.scan(max_subsystems=20)

    print("Scanned subsystems:", ",".join(sub.name for sub in res.scanned_subsystems))
    print("Changesets:")
    for cs in res.changesets:
        print(cs.title)
        for commit in cs.commits:
            print(commit.message)
            print(commit.diff)
            print()
