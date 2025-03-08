import * as path from "path";
import * as os from "os";
import * as fs from "fs/promises";
import * as child_process from "child_process";
import { simpleGit } from "simple-git";
import axios, { AxiosInstance } from "axios";

// Utility functions

/**
 * Memoize a function to cache its results
 */
function memoize<T extends (...args: any[]) => any>(fn: T): T {
  const cache = new Map<string, ReturnType<T>>();

  return ((...args: Parameters<T>): ReturnType<T> => {
    const key = JSON.stringify(args);
    if (cache.has(key)) {
      return cache.get(key) as ReturnType<T>;
    }
    const result = fn(...args);
    cache.set(key, result);
    return result;
  }) as T;
}

/**
 * Base model class for API responses
 */
class APIModel {
  constructor(data: Record<string, any>) {
    Object.assign(this, data);
  }
}

/**
 * A Bismuth organization
 */
export class Organization extends APIModel {
  id: number;
  name: string;

  constructor(data: Record<string, any>) {
    super(data);
    this.id = data.id;
    this.name = data.name;
  }

  apiPrefix(): string {
    return `/organizations/${this.id}`;
  }
}

/**
 * Search result location
 */
export interface V1SearchResult {
  type: string;
  file: string;
  startLine: number;
  endLine: number | null;
}

export interface V1ReviewBug {
  description: string;
  file: string;
  start_line: number;
  end_line: number;
  suggested_fix: string;
}

export interface V1ReviewResult {
  message: string;
  bugs: V1ReviewBug[];
}

/**
 * A location in a file
 */
export class Location {
  file: string;
  line: number;

  constructor(file: string, line: number) {
    this.file = file;
    this.line = line;
  }

  static fromSearchResult(result: V1SearchResult): Location {
    return new Location(result.file, result.startLine);
  }

  toJSON(): Record<string, any> {
    return {
      file: this.file,
      line: this.line,
    };
  }
}

export interface GitHubAppInstall {
  installationId: number;
}

/**
 * A Bismuth project branch
 */
export class Branch extends APIModel {
  id: number;
  name: string;
  project: Project;
  private api: BismuthClient;

  constructor(data: Record<string, any>, project: Project, api: BismuthClient) {
    super(data);
    this.id = data.id;
    this.name = data.name;
    this.project = project;
    this.api = api;
  }

  apiPrefix(): string {
    return `${this.project.apiPrefix()}/features/${this.id}`;
  }

  /**
   * Search for code relevant to the given query in the branch.
   */
  async search(query: string, top: number = 10): Promise<V1SearchResult[]> {
    const response = await this.api.client.get(`${this.apiPrefix()}/search`, {
      params: {
        query,
        top,
      },
    });
    return response.data.map((result: any) => ({
      type: result.type,
      file: result.file,
      startLine: result.start_line,
      endLine: result.end_line,
    }));
  }

  /**
   * Run the Bismuth agent on the given message
   */
  async generate(
    message: string,
    options: {
      localChanges?: Record<string, string>;
      startLocations?: Location[];
      session?: string;
    } = {}
  ): Promise<string> {
    const { localChanges = {}, startLocations, session } = options;

    const response = await this.api.client.post(
      `${this.apiPrefix()}/generate`,
      {
        message,
        local_changes: localChanges,
        start_locations: startLocations
          ? startLocations.map((loc) => loc.toJSON())
          : undefined,
        session,
      },
      {
        timeout: 0, // No timeout
      }
    );

    if (response.data.partial) {
      console.warn(
        `Potentially incomplete generation due to ${response.data.error}`
      );
    }

    return response.data.diff;
  }

  /**
   * Summarize the changes in the given unified diff
   */
  async summarizeChanges(diff: string): Promise<string> {
    const response = await this.api.client.post(
      `${this.apiPrefix()}/summarize`,
      {
        diff,
      },
      {
        timeout: 0,
      }
    );

    return response.data.message;
  }

  /**
   * Review changes in the given files (compared to HEAD) for bugs.
   * message is a commit message or similar "intent" of the changes.
   * changed_files is a dict of file paths to their new content.
   */
  async reviewChanges(
    message: string,
    changedFiles: Record<string, string>
  ): Promise<V1ReviewResult> {
    const response = await this.api.client.post(
      `${this.apiPrefix()}/review`,
      {
        message,
        changes: changedFiles,
      },
      {
        timeout: 0,
      }
    );

    return response.data;
  }
}

/**
 * A Bismuth project
 */
export class Project extends APIModel {
  id: number;
  name: string;
  hash: string;
  branches: Branch[];
  cloneToken: string;
  githubRepo?: string;
  githubAppInstall?: GitHubAppInstall;
  private api: BismuthClient;

  constructor(data: Record<string, any>, api: BismuthClient) {
    super(data);
    this.id = data.id;
    this.name = data.name;
    this.hash = data.hash;
    this.cloneToken = data.cloneToken;
    this.githubRepo = data.githubRepo;
    this.githubAppInstall = data.githubAppInstall;
    this.api = api;

    // Initialize branches (features in the API)
    this.branches = (data.features || []).map(
      (f: any) => new Branch(f, this, api)
    );
  }

  apiPrefix(): string {
    return `${this.api.organization!!.apiPrefix()}/projects/${this.id}`;
  }

  /**
   * Refresh project data
   */
  async refresh(): Promise<void> {
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
  async synchronizeGitLocal(repoPath: string): Promise<void> {
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

    const git = simpleGit(fullPath);
    const parsedUrl = new URL(this.api.baseUrl);
    parsedUrl.pathname = `/git/${this.hash}`;
    parsedUrl.username = "git";
    parsedUrl.password = this.cloneToken;

    // Check if bismuth remote exists
    const remotes = await git.getRemotes(true);
    const bismuthRemote = remotes.find((r) => r.name === "bismuth");

    if (!bismuthRemote) {
      await git.addRemote("bismuth", parsedUrl.toString());
    } else {
      await git.remote(["set-url", "bismuth", parsedUrl.toString()]);
    }

    const currentBranch = await git.revparse(["--abbrev-ref", "HEAD"]);
    await git.push("bismuth", currentBranch, ["--force"]);

    await this.refresh();
  }

  /**
   * Synchronize the repository stored by Bismuth with a git remote URL
   */
  async synchronizeGitRemote(gitUrl: string): Promise<void> {
    if (this.githubAppInstall) {
      throw new Error("Cannot synchronize a project linked to GitHub repo");
    }

    const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "bismuth-"));
    try {
      await simpleGit().clone(gitUrl, tempDir);
      await this.synchronizeGitLocal(tempDir);
    } finally {
      // Clean up temp directory
      await fs.rm(tempDir, { recursive: true, force: true });
    }
  }

  /**
   * Delete the project
   */
  async delete(): Promise<void> {
    await this.api.client.delete(this.apiPrefix());
  }

  /**
   * Get a branch by name
   */
  getBranch(branchName: string): Branch {
    const branch = this.branches.find((b) => b.name === branchName);
    if (!branch) {
      throw new Error(`No such branch: ${branchName}`);
    }
    return branch;
  }
}

/**
 * Main client for the Bismuth API
 */
export class BismuthClient {
  apiKey: string;
  baseUrl: string;
  private organizationId?: number;
  organization?: Organization;
  client: AxiosInstance;

  constructor(options: {
    apiKey: string;
    organizationId?: number;
    baseUrl?: string;
  }) {
    const {
      apiKey,
      organizationId,
      baseUrl = process.env.BISMUTH_API || "https://api.bismuth.cloud",
    } = options;

    this.apiKey = apiKey;
    this.organizationId = organizationId;
    this.baseUrl = baseUrl;

    this.client = axios.create({
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
   * List all organizations the user is a member of
   */
  listOrganizations = memoize(async (): Promise<Organization[]> => {
    const response = await this.client.get("/organizations");
    return response.data.map((org: any) => new Organization(org));
  });

  /**
   * Get the active organization
   */
  async getOrganization(): Promise<Organization> {
    if (this.organization) {
      return this.organization;
    }

    if (!this.organizationId) {
      const organizations = await this.listOrganizations();
      if (organizations.length > 1) {
        throw new Error(
          "Multiple organizations found - organizationId must be specified"
        );
      }
      this.organizationId = organizations[0].id;
    }

    const response = await this.client.get(
      `/organizations/${this.organizationId}`
    );
    this.organization = new Organization(response.data);
    return this.organization;
  }

  /**
   * Get a project by name or ID
   */
  async getProject(nameOrId: string | number): Promise<Project> {
    const organization = await this.getOrganization();

    if (typeof nameOrId === "string") {
      const response = await this.client.get(
        `${organization.apiPrefix()}/projects/list`
      );

      for (const project of response.data.projects) {
        if (project.name === nameOrId) {
          return new Project(project, this);
        }
      }
      throw new Error("No such project");
    } else if (typeof nameOrId === "number") {
      const response = await this.client.get(
        `${organization.apiPrefix()}/projects/${nameOrId}`
      );
      return new Project(response.data, this);
    } else {
      throw new Error(
        `getProject accepts project name (string) or id (number), not ${typeof nameOrId}`
      );
    }
  }

  /**
   * Load a project from a local git repository
   */
  async loadProject(
    repoPath: string,
    create: boolean = true
  ): Promise<Project> {
    const fullPath = path.resolve(repoPath);
    const gitDirExists = await fs
      .stat(path.join(fullPath, ".git"))
      .then(() => true)
      .catch(() => false);

    if (!gitDirExists) {
      throw new Error(`${fullPath} is not a git repository`);
    }

    const organization = await this.getOrganization();
    const git = simpleGit(fullPath);

    let bismuthRemote;
    try {
      bismuthRemote = (await git.getRemotes(true)).find(
        (r) => r.name === "bismuth"
      );
    } catch (e) {
      bismuthRemote = undefined;
    }

    if (!bismuthRemote) {
      if (!create) {
        throw new Error("No Bismuth remote found");
      }

      const response = await this.client.post(
        `${organization.apiPrefix()}/projects`,
        { name: path.basename(fullPath) }
      );

      const project = new Project(response.data, this);
      await project.synchronizeGitLocal(fullPath);
      return project;
    } else {
      const remoteUrl = new URL(bismuthRemote.refs.fetch);
      const cloneToken = remoteUrl.password;

      const response = await this.client.get(
        `${organization.apiPrefix()}/projects/list`
      );

      for (const projectData of response.data.projects) {
        if (projectData.cloneToken === cloneToken) {
          const project = new Project(projectData, this);
          await project.refresh();
          return project;
        }
      }

      throw new Error(
        "Couldn't find project, but repo already has Bismuth remote"
      );
    }
  }
}

/**
 * Apply a diff returned by generate() to the repo
 * Returns true if the patch was applied successfully, false otherwise
 */
export async function applyDiff(
  repoPath: string,
  diff: string
): Promise<boolean> {
  try {
    return new Promise<boolean>((resolve) => {
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
  } catch (error) {
    return false;
  }
}
