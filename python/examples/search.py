import logging
import os
import pathlib
from bismuthsdk import BismuthClient

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("bismuthsdk").setLevel(logging.DEBUG)
    logging.getLogger("git").setLevel(logging.DEBUG)

    api = BismuthClient(api_key=os.environ["BISMUTH_API_KEY"])
    project = api.load_project(pathlib.Path(__file__).parent.parent.parent)
    results = project.get_branch("main").search("query", top=3)
    print(results)
