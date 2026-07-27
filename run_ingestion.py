import os
from dotenv import load_dotenv
from src.ingestion.github_client import GitHubAPIClient
from src.utils.logger import setup_logger

logger = setup_logger("run_ingestion")

def main():
    load_dotenv()
    
    # Target repository for sample support ticket dataset
    OWNER = "pallets"
    REPO = "flask"
    MAX_ISSUES = 25  # Ingest 25 real open-source issues for inspection
    
    client = GitHubAPIClient()
    issues = client.fetch_repository_issues(
        owner=OWNER,
        repo=REPO,
        state="all",
        max_issues=MAX_ISSUES
    )
    
    output_path = os.path.join("data", "raw", f"{OWNER}_{REPO}_raw_issues.json")
    client.save_raw_issues(issues, output_path)
    
    logger.info("Ingestion execution complete!")
    logger.info(f"Inspect the raw output file at: {output_path}")

if __name__ == "__main__":
    main()
