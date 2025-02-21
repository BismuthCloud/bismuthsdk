from functools import wraps
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from typing import Union, Optional
import asyncio
import git
import os
import httpx
import tempfile
import urllib.parse


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
    )


class Organization(APIModel):
    """
    A Bismuth organization
    """

    id: int
    name: str

    @property
    def _api_prefix(self) -> str:
        return "/organizations/{self.id}"


class BismuthClient:
    api_key: str
    base_url: str
    _client: httpx.AsyncClient

    def __init__(
        self,
        api_key: str,
        base_url: str = os.environ.get("BISMUTH_API", "https://api.bismuth.cloud"),
    ):
        self.api_key = api_key
        self.base_url = base_url

        self._async_client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @memoize
    async def list_organizations_async(self) -> list[Organization]:
        """
        List all organizations the user is a member of.
        """
        async with self._client:
            r = await self._client.get("/organizations")
            r.raise_for_status()
            return [Organization.model_validate(o) for o in r.json()]

    list_organizations = sync_method(list_organizations_async)

    async def get_project_async(
        self, name_or_id: Union[str, int], organization_id: Optional[int] = None
    ) -> "Project":
        """
        Get a project by name or ID.
        If organization_id is not specified, it will be inferred if there is only one organization.
        """
        if not organization_id:
            organizations = await self.list_organizations_async()
            if len(organizations) > 1:
                raise Exception(
                    "Multiple organizations found - organization_id must be specified"
                )
            organization_id = organizations[0].id

        async with self._client:
            if isinstance(name_or_id, str):
                async with self._client:
                    r = await self._client.get(
                        f"/organizations/{organization_id}/projects/list"
                    )
                    r.raise_for_status()
                    for p in map(Project.model_validate, r.json()):
                        if p.name == name_or_id:
                            p._api = self
                            return p
                    raise ValueError("No such project")
            elif isinstance(name_or_id, int):
                async with self._client:
                    r = await self._client.get(
                        f"/organizations/{organization_id}/projects/{name_or_id}"
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

    async def load_project_async(
        self, repo: Path, organization_id: Optional[int] = None, create: bool = True
    ) -> "Project":
        """
        Load a project from a local git repository.
        If already imported into Bismuth, return the existing project.
        If not and create is True, create a new project.
        """
        repo = repo.resolve()
        if not (repo / ".git").exists():
            raise ValueError(f"{repo} is not a git repository")

        if not organization_id:
            organizations = await self.list_organizations_async()
            if len(organizations) > 1:
                raise Exception(
                    "Multiple organizations found - organization_id must be specified"
                )
            organization_id = organizations[0].id

        g = git.Repo(repo)
        if g.remotes.bismuth is None:
            # TODO: attempt to associate by name too?
            if not create:
                raise ValueError("No Bismuth remote found")
            async with self._client:
                r = await self._client.post(
                    f"/organizations/{organization_id}/projects",
                    json={"name": repo.name},
                )
                r.raise_for_status()
                p = Project.model_validate(r.json())
                p._api = self
                await p.synchronize_git_local_async(repo)
                return p
        else:
            url = g.remotes.bismuth.url
            clone_token = urllib.parse.urlparse(url).netloc.split(":")[0]
            async with self._client:
                r = await self._client.get(
                    f"/organizations/{organization_id}/projects/list"
                )
                r.raise_for_status()
                for p in map(Project.model_validate, r.json()):
                    if p.clone_token == clone_token:
                        p._api = self
                        return p
                raise ValueError(
                    "Couldn't find project, but repo already has Bismuth remote"
                )

    load_project = sync_method(load_project_async)


class GitHubAppInstall(BaseModel):
    installation_id: int


class Project(APIModel):
    _api: BismuthClient
    id: int
    name: str
    hash: str
    branches: list["Branch"] = Field(serialization_alias="features")
    clone_token: str = Field(serialization_alias="cloneToken")
    github_repo: Optional[str]
    github_app_install: Optional[GitHubAppInstall]
    organization: Organization

    @property
    def _api_prefix(self) -> str:
        return f"{self.organization._api_prefix}/projects/{self.id}"

    async def _refresh(self):
        async with self._api._client:
            r = await self._api._client.get(self._api_prefix)
            r.raise_for_status()
            new = Project.model_validate(r.json())
            self.branches = new.branches

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
            netloc=f"git:{self.clone_token}@{url.hostname}",
        )
        try:
            g.create_remote("bismuth", urllib.parse.urlunparse(url))
        except git.GitCommandError:
            g.remotes.bismuth.set_url(urllib.parse.urlunparse(url))
        await asyncio.to_thread(
            g.remotes.bismuth.push,
            refspec=f"refs/heads/*:refs/remotes/bismuth/*",
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
            await asyncio.to_thread(git.Repo.clone_from, git_url, tmpdir)
            await self.synchronize_git_local_async(Path(tmpdir))

    synchronize_git_remote = sync_method(synchronize_git_remote_async)

    async def get_branch_async(self, branch: str) -> "Branch":
        for b in self.branches:
            if b.name == branch:
                b._api = self._api
                b.project = self
                return b
        raise ValueError("No such branch")

    get_branch = sync_method(get_branch_async)


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
    start_line: int

    @staticmethod
    def from_search_result(result: V1SearchResult) -> "Location":
        return Location(file=result.file, start_line=result.start_line)


class Branch(APIModel):
    _api: BismuthClient
    id: int
    name: str
    project: Project

    @property
    def _api_prefix(self) -> str:
        return f"{self.project._api_prefix}/features/{self.id}"

    async def search_async(self, query: str, top: int = 10) -> list[V1SearchResult]:
        """
        Search for code relevant to the given query in the branch.
        """
        async with self._api._client:
            r = await self._api._client.post(
                f"{self._api_prefix}/search",
                json={"query": query, "top": top},
            )
            r.raise_for_status()
            return [V1SearchResult.model_validate(l) for l in r.json()]

    search = sync_method(search_async)

    async def generate_async(
        self,
        query: str,
        local_changes: dict[str, str] = {},
        start_locations: Optional[list[Location]] = None,
        context: Optional[str] = None,
    ) -> str:
        """
        Run the Bismuth agent on the given query, applying local_changes (file path -> content) to the repo before processing,
        and seeding the agent with the given start locations. The passed context is a string that will be passed to the agent,
        which can be used to provide general project information, style guidelines, etc.

        Returns a unified diff that can be applied to the repo.
        """
        # TODO: or do we want to treat like a batch api? this returns a id and another method can poll for results
        return ""

    generate = sync_method(generate_async)

    async def summarize_changes_async(self, diff: str) -> str:
        """
        Summarize the changes in the given unified diff in a format suitable for a commit message.
        """
        # TODO: take example messages for style?
        return ""

    summarize_changes = sync_method(summarize_changes_async)
