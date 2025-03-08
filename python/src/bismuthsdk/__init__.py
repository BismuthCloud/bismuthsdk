from functools import wraps
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from pydantic.alias_generators import to_camel
from typing import Union, Optional
import asyncio
import git
import logging
import os
import httpx
import tempfile
import urllib.parse
import subprocess


def sync_method(async_method):
    """
    https://stackoverflow.com/a/55365529
    """

    @wraps(async_method)
    def wrapper(self, *args, **kwargs):
        return asyncio.run(async_method(self, *args, **kwargs))

    if wrapper.__name__.endswith("_async"):
        wrapper.__name__ = wrapper.__name__[: -len("_async")]
    return wrapper


def memoize(func):
    """
    (c) 2021 Nathan Henrie, MIT License
    https://n8henrie.com/2021/11/decorator-to-memoize-sync-or-async-functions-in-python/
    """
    cache = {}

    async def memoized_async_func(*args, **kwargs):
        key = (args, frozenset(sorted(kwargs.items())))
        if key in cache:
            return cache[key]
        result = await func(*args, **kwargs)
        cache[key] = result
        return result

    def memoized_sync_func(*args, **kwargs):
        key = (args, frozenset(sorted(kwargs.items())))
        if key in cache:
            return cache[key]
        result = func(*args, **kwargs)
        cache[key] = result
        return result

    if asyncio.iscoroutinefunction(func):
        return memoized_async_func
    return memoized_sync_func


class APIModel(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel,
    )
    _logger: logging.Logger = PrivateAttr(
        default_factory=lambda: logging.getLogger(__name__)
    )


class Organization(APIModel):
    """
    A Bismuth organization
    """

    id: int
    name: str

    def _api_prefix(self) -> str:
        return f"/organizations/{self.id}"


class BismuthClient:
    api_key: str
    _organization_id: Optional[int]
    organization: Organization = None  # type: ignore
    base_url: str
    _logger: logging.Logger

    def __init__(
        self,
        api_key: str,
        organization_id: Optional[int] = None,
        base_url: str = os.environ.get("BISMUTH_API", "https://api.bismuth.cloud"),
    ):
        self.api_key = api_key
        self._organization_id = organization_id
        self.base_url = base_url

        self._logger = logging.getLogger(__name__)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
        }

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            auth=httpx.BasicAuth("", self.api_key),
            headers=self._headers,
        )

    @memoize
    async def list_organizations_async(self) -> list[Organization]:
        """
        List all organizations the user is a member of.
        """
        self._logger.debug("Listing organizations")
        async with self.client() as client:
            r = await client.get("/organizations")
            r.raise_for_status()
            return [Organization.model_validate(o) for o in r.json()]

    list_organizations = sync_method(list_organizations_async)

    async def get_organization(self) -> Organization:
        if self.organization:
            return self.organization

        if not self._organization_id:
            organizations = await self.list_organizations_async()
            if len(organizations) > 1:
                raise Exception(
                    "Multiple organizations found - organization_id must be specified"
                )
            self._organization_id = organizations[0].id
        async with self.client() as client:
            r = await client.get(f"/organizations/{self._organization_id}")
            r.raise_for_status()
            org = Organization.model_validate(r.json())
            self.organization = org
            return org

    async def get_project_async(self, name_or_id: Union[str, int]) -> "Project":
        """
        Get a project by name or ID.
        """
        organization = await self.get_organization()

        async with self.client() as client:
            if isinstance(name_or_id, str):
                r = await client.get(f"{organization._api_prefix()}/projects/list")
                r.raise_for_status()
                self._logger.debug("Matching project by name")
                for p in map(Project.model_validate, r.json()['projects']):
                    if p.name == name_or_id:
                        p._api = self
                        await p._refresh()
                        return p
                raise ValueError("No such project")
            elif isinstance(name_or_id, int):
                r = await client.get(
                    f"{organization._api_prefix()}/projects/{name_or_id}"
                )
                r.raise_for_status()
                p = Project.model_validate(r.json())
                p._api = self
                return p
            else:
                raise ValueError(
                    f"get_project accepts project name (str) or id (int), not {type(name_or_id)}"
                )

    get_project = sync_method(get_project_async)

    async def load_project_async(self, repo: Path, create: bool = True) -> "Project":
        """
        Load a project from a local git repository.
        If already imported into Bismuth, return the existing project.
        If not and create is True, create a new project.
        """
        repo = repo.resolve()
        if not (repo / ".git").exists():
            raise ValueError(f"{repo} is not a git repository")

        organization = await self.get_organization()

        g = git.Repo(repo)
        try:
            bismuth_remote = g.remote("bismuth")
        except ValueError:
            bismuth_remote = None

        async with self.client() as client:
            if bismuth_remote is None:
                # TODO: attempt to associate by name too?
                if not create:
                    raise ValueError("No Bismuth remote found")
                self._logger.info("Creating project")
                r = await client.post(
                    f"{organization._api_prefix()}/projects",
                    json={"name": repo.name},
                )
                r.raise_for_status()
                p = Project.model_validate(r.json())
                p._api = self
                await p.synchronize_git_local_async(repo)
                return p
            else:
                clone_token = urllib.parse.urlparse(bismuth_remote.url).password
                r = await client.get(f"{organization._api_prefix()}/projects/list")
                r.raise_for_status()
                self._logger.debug("Matching project by clone token")
                for p in map(Project.model_validate, r.json()["projects"]):
                    if p.clone_token == clone_token:
                        p._api = self
                        await p._refresh()
                        return p
                raise ValueError(
                    "Couldn't find project, but repo already has Bismuth remote"
                )

    load_project = sync_method(load_project_async)


class GitHubAppInstall(APIModel):
    installation_id: int


class Project(APIModel):
    _api: BismuthClient
    id: int
    name: str
    hash: str
    branches: list["Branch"] = Field(alias="features")
    clone_token: str
    github_repo: Optional[str]
    github_app_install: Optional[GitHubAppInstall]

    def _api_prefix(self) -> str:
        return f"{self._api.organization._api_prefix()}/projects/{self.id}"

    async def _refresh(self):
        self._logger.debug("Refreshing project branches")
        async with self._api.client() as client:
            r = await client.get(self._api_prefix())
            r.raise_for_status()
            new = Project.model_validate(r.json())
            self.branches = new.branches
            for b in self.branches:
                b._api = self._api
                b.project = self

    async def synchronize_git_local_async(self, repo: Path):
        """
        Synchronize the repository stored by Bismuth with the given local repo.
        """
        if self.github_app_install is not None:
            raise ValueError("Cannot synchronize a project linked to GitHub repo")

        if not (repo / ".git").exists():
            raise ValueError(f"{repo} is not a git repository")
        g = git.Repo(repo)
        url = urllib.parse.urlparse(f"{self._api.base_url}/git/{self.hash}")
        url = url._replace(
            netloc=f"git:{self.clone_token}@{url.netloc}",
        )

        try:
            g.create_remote("bismuth", urllib.parse.urlunparse(url))
            self._logger.info("Created Bismuth remote")
        except git.GitCommandError:
            g.remotes.bismuth.set_url(urllib.parse.urlunparse(url))
            self._logger.debug("Updated Bismuth remote")

        self._logger.info("Pushing to Bismuth remote")
        await asyncio.to_thread(
            g.remotes.bismuth.push,
            refspec=g.active_branch.name,
            force=True,
        )

        await self._refresh()

    synchronize_git_local = sync_method(synchronize_git_local_async)

    async def synchronize_git_remote_async(self, git_url: str):
        """
        Synchronize the repository stored by Bismuth with a git remote URL.
        """
        if self.github_app_install is not None:
            raise ValueError("Cannot synchronize a project linked to GitHub repo")

        with tempfile.TemporaryDirectory() as tmpdir:
            self._logger.info("Cloning remote")
            await asyncio.to_thread(git.Repo.clone_from, git_url, tmpdir)
            await self.synchronize_git_local_async(Path(tmpdir))

    synchronize_git_remote = sync_method(synchronize_git_remote_async)

    def get_branch(self, branch: str) -> "Branch":
        for b in self.branches:
            if b.name == branch:
                return b
        raise ValueError("No such branch")

    async def delete_async(self):
        """
        Delete the project.
        """
        async with self._api.client() as client:
            r = await client.delete(self._api_prefix())
            r.raise_for_status()

    delete = sync_method(delete_async)


class V1SearchResult(BaseModel):
    """
    A search result location.
    """

    # The type of the location, e.g. "FILE", "CLASS", "FUNCTION"
    type: str
    # The file path
    file: str
    # The starting line number (1-indexed, inclusive)
    start_line: int
    # The ending line number (1-indexed, exclusive)
    # May not be present for FILE types. If not present, the result is the entire file.
    end_line: Optional[int]


class Location(BaseModel):
    """
    A location in a file.
    """

    file: str
    # 1-indexed line number in the file
    line: int

    @staticmethod
    def from_search_result(result: V1SearchResult) -> "Location":
        return Location(file=result.file, line=result.start_line)


class V1ReviewBug(BaseModel):
    """
    A bug found in a code review, with a suggested fix.
    """

    # A description of the bug
    description: str
    # The file the bug was found in
    file: str
    # The starting line number (1-indexed, inclusive)
    start_line: int
    # The ending line number (1-indexed, exclusive)
    end_line: int
    # A suggested fix for the bug (fully replacing the lines)
    suggested_fix: str


class V1ReviewResult(BaseModel):
    # A summary message of the code review
    message: str
    # The list of bugs found in the code review
    bugs: list[V1ReviewBug]


class V1ScanCommit(BaseModel):
    """
    A single commit in a proposed changeset.
    """

    # The commit message
    message: str
    # The `git diff` of the commit
    diff: str


class V1ScanChangeset(BaseModel):
    """
    A proposed changeset to the codebase to fix a single discovered issue.
    """

    # The title of the changeset
    title: str
    # A description of the changeset
    body: str
    # The commits in the changeset
    commits: list[V1ScanCommit]


class V1ScanSubsystem(BaseModel):
    """
    A subsystem of the codebase that was scanned.
    """

    # A name for the subsystem
    name: str
    # The files in the subsystem
    files: list[str]


class V1ScanResult(BaseModel):
    # The list of subsystems that were scanned
    scanned_subsystems: list[V1ScanSubsystem]
    # The list of changesets that were proposed
    changesets: list[V1ScanChangeset]


class Branch(APIModel):
    _api: BismuthClient
    id: int
    name: str
    project: Project = None  # type: ignore

    def _api_prefix(self) -> str:
        return f"{self.project._api_prefix()}/features/{self.id}"

    async def search_async(self, query: str, top: int = 10) -> list[V1SearchResult]:
        """
        Search for code relevant to the given query in the branch.
        """
        async with self._api.client() as client:
            r = await client.get(
                f"{self._api_prefix()}/search",
                params={"query": query, "top": top},
            )
            r.raise_for_status()
            return [V1SearchResult.model_validate(l) for l in r.json()]

    search = sync_method(search_async)

    async def generate_async(
        self,
        message: str,
        local_changes: dict[str, str] = {},
        start_locations: Optional[list[Location]] = None,
        session: Optional[str] = None,
    ) -> str:
        """
        Run the Bismuth agent on the given message, applying local_changes (file path -> content) to the repo before processing,
        and seeding the agent with the given start locations.

        If start_locations is not provided, the agent will attempt to find relevant locations in the codebase.
        If session is provided, the agent will create or continue from the previous session with the same name.

        Returns a unified diff that can be applied to the repo with apply_diff()
        """
        async with self._api.client() as client:
            r = await client.post(
                f"{self._api_prefix()}/generate",
                json={
                    "message": message,
                    "local_changes": local_changes,
                    "start_locations": (
                        [l.model_dump() for l in start_locations]
                        if start_locations
                        else None
                    ),
                    "session": session,
                },
                timeout=None,
            )
            r.raise_for_status()
            j = r.json()
            if j["partial"]:
                self._logger.warning(
                    f"Potentially incomplete generation due to {j['error']}"
                )
            return r.json()["diff"]

    generate = sync_method(generate_async)

    async def summarize_changes_async(self, diff: str) -> str:
        """
        Summarize the changes in the given unified diff in a format suitable for a commit message.
        """
        # TODO: take example messages for style?
        async with self._api.client() as client:
            r = await client.post(
                f"{self._api_prefix()}/summarize",
                json={
                    "diff": diff,
                },
                timeout=None,
            )
            r.raise_for_status()
            return r.json()["message"]

    summarize_changes = sync_method(summarize_changes_async)

    async def review_changes_async(
        self, message: str, changed_files: dict[str, str]
    ) -> V1ReviewResult:
        """
        Review changes in the given files (compared to HEAD) for bugs.
        message is a commit message or similar "intent" of the changes.
        changed_files is a dict of file paths to their new content.
        """
        async with self._api.client() as client:
            r = await client.post(
                f"{self._api_prefix()}/review",
                json={
                    "message": message,
                    "changes": changed_files,
                },
                timeout=None,
            )
            r.raise_for_status()
            return V1ReviewResult.model_validate(r.json())

    review_changes = sync_method(review_changes_async)

    async def scan_async(self, max_subsystems: int = 5) -> V1ScanResult:
        """
        Scan the project for bugs, covering at most max_subsystems subsystems.
        Subsystems are dynamically determined by the agent, and up to max_subsystems are randomly selected to be scanned.
        """
        async with self._api.client() as client:
            r = await client.post(
                f"{self._api_prefix()}/scan",
                json={
                    "max_subsystems": max_subsystems,
                },
                timeout=None,
            )
            r.raise_for_status()
            return V1ScanResult.model_validate(r.json())

    scan = sync_method(scan_async)


def apply_diff(repo: Path, diff: str) -> bool:
    """
    Apply a diff returned by generate() to the repo.
    Returns True if the patch was applied successfully, False otherwise.
    """
    try:
        process = subprocess.Popen(
            ["patch", "-p0"], cwd=repo, stdin=subprocess.PIPE, text=True
        )

        process.communicate(input=diff)

        if process.returncode != 0:
            return False

        return True
    except subprocess.SubprocessError:
        return False
