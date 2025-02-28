import * as fs from "fs/promises";
import * as path from "path";
import * as child_process from "child_process";
import { BismuthClient, applyDiff } from "bismuthsdk";

async function runCommand(
  command: string,
  args: string[],
  cwd: string
): Promise<void> {
  return new Promise((resolve, reject) => {
    const process = child_process.spawn(command, args, {
      cwd,
      stdio: "inherit",
    });

    process.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(
          new Error(
            `Command ${command} ${args.join(" ")} failed with code ${code}`
          )
        );
      }
    });
  });
}

async function main() {
  const exampleDir = path.resolve("/tmp/bismuthsdk_example");

  // Create test repository if it doesn't exist
  try {
    await fs.stat(exampleDir);
  } catch (error) {
    await fs.mkdir(exampleDir, { recursive: true });
    await runCommand("git", ["init"], exampleDir);

    await fs.writeFile(
      path.join(exampleDir, "test.py"),
      "print('Hello, world!')\n"
    );

    await runCommand("git", ["add", "."], exampleDir);
    await runCommand("git", ["commit", "-m", "Initial commit"], exampleDir);
  }

  // Initialize Bismuth client
  const api = new BismuthClient({
    apiKey: process.env.BISMUTH_API_KEY,
  });

  // Load the project and get the main branch
  const project = await api.loadProject(exampleDir);
  const branch = project.getBranch("main");

  /**
   * Run the Bismuth agent on the given message, applying local_changes (file path -> content) to the repo before processing,
   * and seeding the agent with the given start locations.
   *
   * If startLocations is not provided, the agent will attempt to find relevant locations in the codebase.
   * If session is provided, the agent will create or continue from the previous session with the same name.
   *
   * Returns a unified diff that can be applied to the repo.
   */
  const diff = await branch.generate("change test.py to say goodbye world", {
    localChanges: {},
    startLocations: undefined,
    session: undefined,
  });

  console.log(diff);

  // Apply the diff
  const success = await applyDiff(exampleDir, diff);
  if (!success) {
    console.log("Failed to apply patch?");
  }

  // Summarize changes for commit message
  const commitMsg = await branch.summarizeChanges(diff);
  console.log(commitMsg);
}

// Run the main function, handling any errors
main().catch((error) => {
  console.warn("An error occurred:", error);
  process.exit(1);
});
