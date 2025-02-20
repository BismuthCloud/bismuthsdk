# SPDX-FileCopyrightText: 2025-present Nick Gregory <nick@bismuth.cloud>
#
# SPDX-License-Identifier: MIT
from dataclasses import dataclass
from pathlib import Path
from typing import Union, Optional
import os
import httpx

class BismuthClient:
    api_key: str
    base_url: str
    _client: httpx.Client
    _async_client: httpx.AsyncClient

    def __init__(
        self,
        api_key: str,
        base_url: str = os.environ.get("BISMUTH_API", "https://api.bismuth.cloud"),
    ):
        self.api_key = api_key
        self.base_url = base_url

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=self._headers,
        )
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

    def close(self):
        """Close all HTTP connections"""
        self._client.close()

    async def aclose(self):
        """Close all async HTTP connections"""
        await self._async_client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get_project(self, name_or_id: Union[str, int], organization_id: Optional[int] = None) -> 'Project':
        if isinstance(name_or_id, str):
            return Project(self, 123, name_or_id)
        elif isinstance(name_or_id, int):
            return Project(self, name_or_id, "name")
        else:
            raise ValueError(f"get_project accepts project name (str) or id (int), not {type(name_or_id)}")


@dataclass
class Location:
    """
    A specific line in a file in a project.
    """
    file: str
    line: int


# TODO: branch?
class Project:
    _client: BismuthClient
    id: int
    name: str

    def __init__(self, client: BismuthClient, id: int, name: str):
        self._client = client
        self.id = id
        self.name = name

    def synchronize_git_local(self, repo: Path):
        pass

    def synchronize_git_remote(self, git_url: str):
        pass

    def search(self, query: str, top: int = 10) -> list[Location]:
        """
        Search for code relevant to the given query in the project.
        """
        return []

    def generate(self, query: str, local_changes: dict[str, str] = {}, start_locations: Optional[list[Location]] = None) -> str:
        """
        Run the Bismuth agent on the given query, applying local_changes (file path -> content) to the repo before processing,
        and seeding the agent with the given start locations.
        Returns a unified diff that can be applied to the repo.
        """
        return ""
