import * as path from "path";
import * as fs from "fs/promises";
import * as os from "os";
import { simpleGit } from "simple-git";
import { BismuthClient } from "./index";
import { jest } from "@jest/globals";

// Mock for simpleGit push to avoid actually trying to push to a non-existent remote
jest.mock("simple-git", () => {
  const originalModule = jest.requireActual(
    "simple-git"
  ) as typeof import("simple-git");
  return {
    __esModule: true,
    ...originalModule,
    simpleGit: (workingDir: string) => {
      const git = originalModule.simpleGit(workingDir);
      git.push = jest.fn() as any;
      return git;
    },
  };
});

describe("Bismuth SDK Tests", () => {
  let bismuthClient: BismuthClient;
  let testRepoPath: string;

  beforeAll(async () => {
    const wiremockUrl = "http://localhost:9090";

    bismuthClient = new BismuthClient({
      apiKey: "test-api-key",
      baseUrl: wiremockUrl,
    });
  });

  beforeEach(async () => {
    testRepoPath = await fs.mkdtemp(path.join(os.tmpdir(), "bismuth-test-"));
    const git = simpleGit(testRepoPath);

    await git.init();
    await git.addConfig("user.name", "Test User");
    await git.addConfig("user.email", "test@example.com");

    const testFilePath = path.join(testRepoPath, "test.py");
    await fs.writeFile(testFilePath, "print('Hello, world!')\n");

    await git.add(".");
    await git.commit("Initial commit");
  });

  afterEach(async () => {
    const git = simpleGit(testRepoPath);
    try {
      await git.raw(["gc"]);
    } catch (e) {}
    await fs.rm(testRepoPath, { recursive: true, force: true });
  });

  describe("CRUD Functionality", () => {
    test("Get project by ID", async () => {
      const project = await bismuthClient.getProject(1);
      const branch = project.getBranch("main");
      await branch.search("query");

      expect(project.id).toBe(1);
      expect(project.name).toBe("Example Project");
      expect(branch.name).toBe("main");
    });

    test("Get project by name", async () => {
      const project = await bismuthClient.getProject("Example Project");
      const branch = project.getBranch("main");
      await branch.search("query");

      expect(project.id).toBe(1);
      expect(project.name).toBe("Example Project");
      expect(branch.name).toBe("main");
    });

    test("Load project with no remote", async () => {
      const p = await bismuthClient.loadProject(testRepoPath);
      const branch = p.getBranch("main");
      await branch.search("query");

      expect(p.id).toBe(1);
      expect(p.name).toBe(testRepoPath.split(path.sep).pop());
      expect(branch.name).toBe("main");
    });

    test("Load project with existing remote", async () => {
      // Create a bismuth remote
      const git = simpleGit(testRepoPath);
      await git.addRemote(
        "bismuth",
        "http://git:clone-token-123@localhost:8080/git/test"
      );

      const p = await bismuthClient.loadProject(testRepoPath);
      const branch = p.getBranch("main");
      await branch.search("query");

      expect(p.id).toBe(1);
      expect(p.name).toBe("Example Project");
    });

    test("Load project with unrecognized remote", async () => {
      // Create a bismuth remote with a token that won't be recognized
      const git = simpleGit(testRepoPath);
      await git.addRemote(
        "bismuth",
        "http://git:some-other-clone-token@localhost:8080/git/test"
      );

      await expect(bismuthClient.loadProject(testRepoPath)).rejects.toThrow(
        "Couldn't find project"
      );
    });
  });

  describe("Generation Functionality", () => {
    test("Search code", async () => {
      const project = await bismuthClient.getProject(1);
      const branch = project.getBranch("main");
      const results = await branch.search("print_hello", 3);

      expect(results.length).toBe(1);
      expect(results[0].file).toBe("test.py");
      expect(results[0].startLine).toBe(1);
      expect(results[0].endLine).toBe(3);
      expect(results[0].type).toBe("FUNCTION");
    });

    test("Generate code changes", async () => {
      const project = await bismuthClient.getProject(1);
      const branch = project.getBranch("main");

      const diff = await branch.generate("change test.py to say goodbye world");

      expect(diff).toContain("--- test.py");
      expect(diff).toContain("+++ test.py");
      expect(diff).toContain("-print('Hello, world!')");
      expect(diff).toContain("+print('Goodbye, world!')");
    });

    test("Summarize changes", async () => {
      const project = await bismuthClient.getProject(1);
      const branch = project.getBranch("main");

      const summary = await branch.summarizeChanges(
        '--- test.py\n+++ test.py\n@@ -1,2 +1,3 @@+"""Print hello world message"""\n print("Hello, world!")\n'
      );

      expect(summary).toBe("Add docstring");
    });

    test("Review changes", async () => {
      const project = await bismuthClient.getProject(1);
      const branch = project.getBranch("main");

      const res = await branch.reviewChanges("update print message", {
        "test.py": "print('Hello, world!')\n",
      });

      expect(res.message).toContain("Found 1 issue in the code");
      expect(res.bugs.length).toBe(1);

      const bug = res.bugs[0];
      expect(bug.file).toBe("test.py");
      expect(bug.description).toBe("Missing docstring");
      expect(bug.suggested_fix).toContain("Print hello world message");
    });

    test("Scan project", async () => {
      const project = await bismuthClient.getProject(1);
      const branch = project.getBranch("main");

      const res = await branch.scan(20);

      expect(res.scanned_subsystems.length).toBe(1);
      expect(res.scanned_subsystems[0].name).toBe("Core");
      expect(res.scanned_subsystems[0].files).toContain("test.py");

      expect(res.changesets.length).toBe(1);
      const changeset = res.changesets[0];
      expect(changeset.title).toBe("Add missing docstrings");

      expect(changeset.commits.length).toBe(1);
      const commit = changeset.commits[0];
      expect(commit.message).toBe("Add docstring");
      expect(commit.diff).toContain("--- test.py");
      expect(commit.diff).toContain('+"""Print hello world message"""');
    });
  });
});
