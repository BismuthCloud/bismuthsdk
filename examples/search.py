import os
import pathlib
from bismuthsdk import BismuthClient

if __name__ == "__main__":
    api = BismuthClient(api_key=os.environ["BISMUTH_API_KEY"])
    project = api.load_project(pathlib.Path(__file__).parent.parent)
    results = project.get_branch("main").search("search", top=3)
    print(results)
