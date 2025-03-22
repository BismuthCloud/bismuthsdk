import pathlib
import shutil
import subprocess
import tempfile
import pytest
import git
import json
from wiremock.testing.testcontainer import wiremock_container
from wiremock.client import Mappings, Mapping
from wiremock.constants import Config
from bismuthsdk import BismuthClient


@pytest.fixture(scope="session")
def wm_docker():
    with wiremock_container(
        image="wiremock/wiremock:3.12.1", verify_ssl_certs=False, secure=False
    ) as wm:
        Config.base_url = wm.get_url("__admin")

        git_repo = git.Repo(".", search_parent_directories=True)
        repo_root = pathlib.Path(git_repo.git.rev_parse("--show-toplevel"))

        with open(repo_root / "testing" / "wiremock-stubs.json") as f:
            mappings = json.loads(f.read())["mappings"]

        Mappings.delete_all_mappings()
        for mapping in mappings:
            Mappings.create_mapping(Mapping.from_dict(mapping))

        yield wm

        Mappings.delete_all_mappings()


@pytest.fixture
def test_repo():
    repo_dir = tempfile.mkdtemp()
    repo_path = pathlib.Path(repo_dir)

    subprocess.run(["git", "init"], cwd=repo_dir)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir)

    test_file = repo_path / "test.py"
    test_file.write_text("print('Hello, world!')\n")

    subprocess.run(["git", "add", "."], cwd=repo_dir)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir)

    yield repo_path

    shutil.rmtree(repo_dir)


@pytest.fixture
def bismuth_client(wm_docker):
    api_key = "test-api-key"
    base_url = wm_docker.get_base_url()

    return BismuthClient(api_key=api_key, base_url=base_url)


class TestCRUD:
    """
    Test that the basic CRUD functionalities of the Bismuth SDK communicate with the API correctly.
    """

    def test_get_project_id(self, bismuth_client):
        project = bismuth_client.get_project(1)
        branch = project.get_branch("main")
        branch.search("query")

    def test_get_project_name(self, bismuth_client):
        project = bismuth_client.get_project("Example Project")
        branch = project.get_branch("main")
        branch.search("query")

    def test_load_project_no_remote(
        self,
        bismuth_client,
        test_repo,
        mocker,
    ):
        mocker.patch("git.Remote.push")
        p = bismuth_client.load_project(test_repo)
        assert p.id == 1
        assert p.name == test_repo.name
        p.get_branch("main").search("query")

    def test_load_project_existing_remote(
        self,
        bismuth_client,
        test_repo,
    ):
        r = git.Repo(test_repo)
        r.create_remote("bismuth", "http://git:clone-token-123@localhost:8080/git/test")
        p = bismuth_client.load_project(test_repo)
        p.get_branch("main").search("query")

    def test_load_project_unrecognized_remote(
        self,
        bismuth_client,
        test_repo,
    ):
        r = git.Repo(test_repo)
        r.create_remote(
            "bismuth", "http://git:some-other-clone-token@localhost:8080/git/test"
        )
        with pytest.raises(ValueError):
            bismuth_client.load_project(test_repo)


class TestGeneration:
    """
    Test that the main generational functionalities of the Bismuth SDK communicate with the API correctly.
    """

    def test_search(self, bismuth_client):
        project = bismuth_client.get_project(1)
        results = project.get_branch("main").search("print_hello", top=3)

        assert len(results) == 1
        assert results[0].file == "test.py"
        assert results[0].start_line == 1
        assert results[0].end_line == 3
        assert results[0].type == "FUNCTION"

    def test_generate(self, bismuth_client):
        project = bismuth_client.get_project(1)
        branch = project.get_branch("main")

        diff = branch.generate(
            "change test.py to say goodbye world",
            local_changes={},
            start_locations=None,
            session=None,
        )

        assert "--- test.py" in diff
        assert "+++ test.py" in diff
        assert "-print('Hello, world!')" in diff
        assert "+print('Goodbye, world!')" in diff

    def test_summarize(self, bismuth_client):
        project = bismuth_client.get_project(1)
        branch = project.get_branch("main")

        summary = branch.summarize_changes(
            '--- test.py\n+++ test.py\n@@ -1,2 +1,3 @@+"""Print hello world message"""\n print("Hello, world!")\n'
        )
        assert summary == "Add docstring"

    def test_review_changes(self, bismuth_client):
        project = bismuth_client.get_project(1)
        branch = project.get_branch("main")

        res = branch.review_changes(
            message="update print message",
            changed_files={"test.py": "print('Hello, world!')\n"},
        )

        assert "Found 1 issue in the code" in res.message
        assert len(res.bugs) == 1

        bug = res.bugs[0]
        assert bug.file == "test.py"
        assert bug.description == "Missing docstring"
        assert "Print hello world message" in bug.suggested_fix

    def test_scan(self, bismuth_client):
        project = bismuth_client.get_project(1)
        branch = project.get_branch("main")

        res = branch.scan(max_subsystems=20)

        assert len(res.scanned_subsystems) == 1
        assert res.scanned_subsystems[0].name == "Core"
        assert "test.py" in res.scanned_subsystems[0].files

        assert len(res.changesets) == 1
        changeset = res.changesets[0]
        assert changeset.title == "Add missing docstrings"

        assert len(changeset.commits) == 1
        commit = changeset.commits[0]
        assert commit.message == "Add docstring"
        assert "--- test.py" in commit.diff
        assert '+"""Print hello world message"""' in commit.diff
