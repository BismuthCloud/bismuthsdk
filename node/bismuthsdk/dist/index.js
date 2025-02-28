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
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.BismuthClient = exports.Project = exports.Branch = exports.Location = exports.Organization = void 0;
exports.applyDiff = applyDiff;
const path = __importStar(require("path"));
const os = __importStar(require("os"));
const fs = __importStar(require("fs/promises"));
const child_process = __importStar(require("child_process"));
const simple_git_1 = require("simple-git");
const axios_1 = __importDefault(require("axios"));
// Utility functions
/**
 * Memoize a function to cache its results
 */
function memoize(fn) {
    const cache = new Map();
    return ((...args) => {
        const key = JSON.stringify(args);
        if (cache.has(key)) {
            return cache.get(key);
        }
        const result = fn(...args);
        cache.set(key, result);
        return result;
    });
}
/**
 * Base model class for API responses
 */
class APIModel {
    constructor(data) {
        Object.assign(this, data);
    }
}
/**
 * A Bismuth organization
 */
class Organization extends APIModel {
    constructor(data) {
        super(data);
        this.id = data.id;
        this.name = data.name;
    }
    apiPrefix() {
        return `/organizations/${this.id}`;
    }
}
exports.Organization = Organization;
/**
 * A location in a file
 */
class Location {
    constructor(file, line) {
        this.file = file;
        this.line = line;
    }
    static fromSearchResult(result) {
        return new Location(result.file, result.startLine);
    }
    toJSON() {
        return {
            file: this.file,
            line: this.line,
        };
    }
}
exports.Location = Location;
/**
 * A Bismuth project branch
 */
class Branch extends APIModel {
    constructor(data, project, api) {
        super(data);
        this.id = data.id;
        this.name = data.name;
        this.project = project;
        this.api = api;
    }
    apiPrefix() {
        return `${this.project.apiPrefix()}/features/${this.id}`;
    }
    /**
     * Search for code relevant to the given query in the branch.
     */
    async search(query, top = 10) {
        const response = await this.api.client.get(`${this.apiPrefix()}/search`, {
            params: {
                query,
                top,
            },
        });
        return response.data.map((result) => ({
            type: result.type,
            file: result.file,
            startLine: result.start_line,
            endLine: result.end_line,
        }));
    }
    /**
     * Run the Bismuth agent on the given message
     */
    async generate(message, options = {}) {
        const { localChanges = {}, startLocations, session } = options;
        const response = await this.api.client.post(`${this.apiPrefix()}/generate`, {
            message,
            local_changes: localChanges,
            start_locations: startLocations
                ? startLocations.map((loc) => loc.toJSON())
                : undefined,
            session,
        }, {
            timeout: 0, // No timeout
        });
        if (response.data.partial) {
            console.warn(`Potentially incomplete generation due to ${response.data.error}`);
        }
        return response.data.diff;
    }
    /**
     * Summarize the changes in the given unified diff
     */
    async summarizeChanges(diff) {
        const response = await this.api.client.post(`${this.apiPrefix()}/summarize`, {
            diff,
        }, {
            timeout: 0,
        });
        return response.data.message;
    }
}
exports.Branch = Branch;
/**
 * A Bismuth project
 */
class Project extends APIModel {
    constructor(data, api) {
        super(data);
        this.id = data.id;
        this.name = data.name;
        this.hash = data.hash;
        this.cloneToken = data.cloneToken;
        this.githubRepo = data.githubRepo;
        this.githubAppInstall = data.githubAppInstall;
        this.api = api;
        // Initialize branches (features in the API)
        this.branches = (data.features || []).map((f) => new Branch(f, this, api));
    }
    apiPrefix() {
        return `${this.api.organization.apiPrefix()}/projects/${this.id}`;
    }
    /**
     * Refresh project data
     */
    async refresh() {
        const response = await this.api.client.get(this.apiPrefix());
        const newProject = new Project(response.data, this.api);
        this.branches = newProject.branches.map((b) => {
            b.project = this;
            return b;
        });
    }
    /**
     * Synchronize the repository stored by Bismuth with the given local repo
     */
    async synchronizeGitLocal(repoPath) {
        if (this.githubAppInstall) {
            throw new Error("Cannot synchronize a project linked to GitHub repo");
        }
        const fullPath = path.resolve(repoPath);
        const gitDirExists = await fs
            .stat(path.join(fullPath, ".git"))
            .then(() => true)
            .catch(() => false);
        if (!gitDirExists) {
            throw new Error(`${fullPath} is not a git repository`);
        }
        const git = (0, simple_git_1.simpleGit)(fullPath);
        const parsedUrl = new URL(this.api.baseUrl);
        parsedUrl.pathname = `/git/${this.hash}`;
        parsedUrl.username = "git";
        parsedUrl.password = this.cloneToken;
        // Check if bismuth remote exists
        const remotes = await git.getRemotes(true);
        const bismuthRemote = remotes.find((r) => r.name === "bismuth");
        if (!bismuthRemote) {
            await git.addRemote("bismuth", parsedUrl.toString());
        }
        else {
            await git.remote(["set-url", "bismuth", parsedUrl.toString()]);
        }
        const currentBranch = await git.revparse(["--abbrev-ref", "HEAD"]);
        await git.push("bismuth", currentBranch, ["--force"]);
        await this.refresh();
    }
    /**
     * Synchronize the repository stored by Bismuth with a git remote URL
     */
    async synchronizeGitRemote(gitUrl) {
        if (this.githubAppInstall) {
            throw new Error("Cannot synchronize a project linked to GitHub repo");
        }
        const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bismuth-"));
        try {
            await (0, simple_git_1.simpleGit)().clone(gitUrl, tempDir);
            await this.synchronizeGitLocal(tempDir);
        }
        finally {
            // Clean up temp directory
            await fs.rm(tempDir, { recursive: true, force: true });
        }
    }
    /**
     * Get a branch by name
     */
    getBranch(branchName) {
        const branch = this.branches.find((b) => b.name === branchName);
        if (!branch) {
            throw new Error(`No such branch: ${branchName}`);
        }
        return branch;
    }
}
exports.Project = Project;
/**
 * Main client for the Bismuth API
 */
class BismuthClient {
    constructor(options) {
        /**
         * List all organizations the user is a member of
         */
        this.listOrganizations = memoize(async () => {
            const response = await this.client.get("/organizations");
            return response.data.map((org) => new Organization(org));
        });
        const { apiKey, organizationId, baseUrl = process.env.BISMUTH_API || "https://api.bismuth.cloud", } = options;
        this.apiKey = apiKey;
        this.organizationId = organizationId;
        this.baseUrl = baseUrl;
        this.client = axios_1.default.create({
            baseURL: this.baseUrl,
            auth: {
                username: "",
                password: this.apiKey,
            },
            headers: {
                "Content-Type": "application/json",
            },
        });
    }
    /**
     * Get the active organization
     */
    async getOrganization() {
        if (this.organization) {
            return this.organization;
        }
        if (!this.organizationId) {
            const organizations = await this.listOrganizations();
            if (organizations.length > 1) {
                throw new Error("Multiple organizations found - organizationId must be specified");
            }
            this.organizationId = organizations[0].id;
        }
        const response = await this.client.get(`/organizations/${this.organizationId}`);
        this.organization = new Organization(response.data);
        return this.organization;
    }
    /**
     * Get a project by name or ID
     */
    async getProject(nameOrId) {
        const organization = await this.getOrganization();
        if (typeof nameOrId === "string") {
            const response = await this.client.get(`${organization.apiPrefix()}/projects/list`);
            for (const project of response.data) {
                if (project.name === nameOrId) {
                    return new Project(project, this);
                }
            }
            throw new Error("No such project");
        }
        else if (typeof nameOrId === "number") {
            const response = await this.client.get(`${organization.apiPrefix()}/projects/${nameOrId}`);
            return new Project(response.data, this);
        }
        else {
            throw new Error(`getProject accepts project name (string) or id (number), not ${typeof nameOrId}`);
        }
    }
    /**
     * Load a project from a local git repository
     */
    async loadProject(repoPath, create = true) {
        const fullPath = path.resolve(repoPath);
        const gitDirExists = await fs
            .stat(path.join(fullPath, ".git"))
            .then(() => true)
            .catch(() => false);
        if (!gitDirExists) {
            throw new Error(`${fullPath} is not a git repository`);
        }
        const organization = await this.getOrganization();
        const git = (0, simple_git_1.simpleGit)(fullPath);
        let bismuthRemote;
        try {
            bismuthRemote = (await git.getRemotes(true)).find((r) => r.name === "bismuth");
        }
        catch (e) {
            bismuthRemote = undefined;
        }
        if (!bismuthRemote) {
            if (!create) {
                throw new Error("No Bismuth remote found");
            }
            const response = await this.client.post(`${organization.apiPrefix()}/projects`, { name: path.basename(fullPath) });
            const project = new Project(response.data, this);
            await project.synchronizeGitLocal(fullPath);
            return project;
        }
        else {
            const remoteUrl = new URL(bismuthRemote.refs.fetch);
            const cloneToken = remoteUrl.password;
            const response = await this.client.get(`${organization.apiPrefix()}/projects/list`);
            for (const projectData of response.data.projects) {
                if (projectData.cloneToken === cloneToken) {
                    const project = new Project(projectData, this);
                    await project.refresh();
                    return project;
                }
            }
            throw new Error("Couldn't find project, but repo already has Bismuth remote");
        }
    }
}
exports.BismuthClient = BismuthClient;
/**
 * Apply a diff returned by generate() to the repo
 * Returns true if the patch was applied successfully, false otherwise
 */
async function applyDiff(repoPath, diff) {
    try {
        return new Promise((resolve) => {
            const process = child_process.spawn("patch", ["-p0"], {
                cwd: repoPath,
                stdio: ["pipe", "inherit", "inherit"],
            });
            process.stdin.write(diff);
            process.stdin.end();
            process.on("close", (code) => {
                resolve(code === 0);
            });
        });
    }
    catch (error) {
        return false;
    }
}
