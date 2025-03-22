"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const path = __importStar(require("path"));
const fs = __importStar(require("fs/promises"));
const os = __importStar(require("os"));
const simple_git_1 = require("simple-git");
const index_1 = require("./index");
const globals_1 = require("@jest/globals");
// Mock for simpleGit push to avoid actually trying to push to a non-existent remote
globals_1.jest.mock("simple-git", () => {
    const originalModule = globals_1.jest.requireActual("simple-git");
    return function () {
        const instance = originalModule.simpleGit();
        instance.push = globals_1.jest
            .fn()
            .mockImplementation(() => Promise.resolve(instance));
        return instance;
    };
});
describe("Bismuth SDK Tests", () => {
    let bismuthClient;
    let testRepoPath;
    beforeAll(async () => {
        const wiremockUrl = "http://localhost:8080";
        // Create the Bismuth client
        bismuthClient = new index_1.BismuthClient({
            apiKey: "test-api-key",
            baseUrl: wiremockUrl,
        });
    });
    beforeEach(async () => {
        // Create a test repository for each test
        testRepoPath = await fs.mkdtemp(path.join(os.tmpdir(), "bismuth-test-"));
        // Initialize git repo
        await (0, simple_git_1.simpleGit)(testRepoPath).init();
        await (0, simple_git_1.simpleGit)(testRepoPath).addConfig("user.name", "Test User");
        await (0, simple_git_1.simpleGit)(testRepoPath).addConfig("user.email", "test@example.com");
        // Create a test file
        const testFilePath = path.join(testRepoPath, "test.py");
        await fs.writeFile(testFilePath, "print('Hello, world!')\n");
        // Commit the file
        await (0, simple_git_1.simpleGit)(testRepoPath).add(".");
        await (0, simple_git_1.simpleGit)(testRepoPath).commit("Initial commit");
    });
    afterEach(async () => {
        // Clean up the test repository
        if (testRepoPath) {
            await fs.rm(testRepoPath, { recursive: true, force: true });
        }
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
            expect(p.name).toBe("Example Project");
            expect(branch.name).toBe("main");
        });
        test("Load project with existing remote", async () => {
            // Create a bismuth remote
            const git = (0, simple_git_1.simpleGit)(testRepoPath);
            await git.addRemote("bismuth", "http://git:clone-token-123@localhost:8080/git/test");
            const p = await bismuthClient.loadProject(testRepoPath);
            const branch = p.getBranch("main");
            await branch.search("query");
            expect(p.id).toBe(1);
            expect(p.name).toBe("Example Project");
        });
        test("Load project with unrecognized remote", async () => {
            // Create a bismuth remote with a token that won't be recognized
            const git = (0, simple_git_1.simpleGit)(testRepoPath);
            await git.addRemote("bismuth", "http://git:some-other-clone-token@localhost:8080/git/test");
            await expect(bismuthClient.loadProject(testRepoPath)).rejects.toThrow("Couldn't find project");
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
            const summary = await branch.summarizeChanges('--- test.py\n+++ test.py\n@@ -1,2 +1,3 @@+"""Print hello world message"""\n print("Hello, world!")\n');
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
