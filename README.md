# bismuthsdk

[![PyPI - Version](https://img.shields.io/pypi/v/bismuthsdk.svg)](https://pypi.org/project/bismuthsdk)

-----

# Python

## Installation

```console
pip install bismuthsdk
```

## Usage

Log in to the Bismuth web UI and create an API key [here](https://app.bismuth.cloud/settings/apikeys).

Then see the [examples directory](./python/examples) for usage of this SDK, or the quickstart samples below:

### Quickstart

#### Importing a repository
```python
from bismuthsdk import BismuthClient
api = BismuthClient(api_key=os.environ["BISMUTH_API_KEY"])
# Given a local repository, load_project will import and upload code to Bismuth as necessary
project = api.load_project(local_repo_dir)
```

#### Searching
```python
print(project.get_branch("main").search("query", top=3))
```

#### Generating code
```python
diff = project.get_branch("main").generate(
    "change test.py to say goodbye world",
    local_changes={},  # path -> contents for locally modified files
    start_locations=None,  # Optional list of Location objects for the agent to start from
    session=None,  # Optional session name to preserve messages and context between generate() calls
)
print(diff)
apply_diff(local_repo_dir, diff)
```

# JS/TS

## Installation

```console
npm install bismuthsdk
```

## Usage

Log in to the Bismuth web UI and create an API key [here](https://app.bismuth.cloud/settings/apikeys).

Then see the [examples directory](./node/examples) for usage of this SDK, or the quickstart samples below:

### Quickstart

#### Importing a repository
```typescript
import { BismuthClient } from "bismuthsdk";
const api = new BismuthClient({
  apiKey: process.env.BISMUTH_API_KEY,
});
// Given a local repository, loadProject will import and upload code to Bismuth as necessary
const project = await api.loadProject(repoDir);
```

#### Searching
```typescript
const results = await project.getBranch("main").search("query", 3);
```

#### Generating code
```typescript
const diff = await branch.generate("change test.py to say goodbye world", {
  localChanges: {},  // path -> contents for locally modified files
  startLocations: undefined,  // Optional list of Location objects for the agent to start from
  session: undefined, // Optional session name to preserve messages and context between generate() calls
});

console.log(diff);
await applyDiff(exampleDir, diff);
```