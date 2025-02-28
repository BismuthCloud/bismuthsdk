import * as path from "path";
import { BismuthClient } from "bismuthsdk";

async function main() {
  // Initialize Bismuth client
  const api = new BismuthClient({
    apiKey: process.env.BISMUTH_API_KEY,
  });

  // Use the repo root
  const repoDir = path.resolve("../..");

  // Load the project and search in the main branch
  const project = await api.loadProject(repoDir);
  const results = await project.getBranch("main").search("query", 3);

  // Print the search results
  console.log(results);
}

// Run the main function, handling any errors
main().catch((error) => {
  console.warn("An error occurred:", error);
  process.exit(1);
});
