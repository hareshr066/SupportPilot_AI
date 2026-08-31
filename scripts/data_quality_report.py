import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Any, Dict, List

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("data_quality_report")

def generate_quality_report(owner: str = "microsoft", repo: str = "vscode") -> Dict[str, Any]:
    repository_name = f"{owner}/{repo}"
    logger.info(f"Generating Data Quality & Completeness Report for: {repository_name}")

    silver_path = Path(settings.processed_data_dir) / "github" / owner / repo / "issues.json"
    if not silver_path.exists():
        fallback = Path(settings.processed_data_dir) / owner / repo / "issues.json"
        if fallback.exists():
            silver_path = fallback
        else:
            raise FileNotFoundError(f"Silver dataset not found at {silver_path}")

    with open(silver_path, "r", encoding="utf-8") as f:
        records: List[Dict[str, Any]] = json.load(f)

    total_issues = len(records)
    if total_issues == 0:
        logger.warning("Empty Silver dataset!")
        return {"total_issues": 0}

    with_body = sum(1 for r in records if r.get("body") and str(r["body"]).strip())
    with_labels = sum(1 for r in records if r.get("labels") and len(r["labels"]) > 0)
    with_comments = sum(1 for r in records if r.get("comments_count", 0) > 0 or (r.get("comments") and len(r["comments"]) > 0))
    with_assignees = sum(1 for r in records if r.get("assignees") and len(r["assignees"]) > 0)
    with_duplicates = sum(1 for r in records if r.get("duplicate_detected") is True)
    with_prs = sum(1 for r in records if r.get("linked_pull_requests") and len(r["linked_pull_requests"]) > 0)
    closed_issues = sum(1 for r in records if r.get("state") == "closed")

    # Ground truth coverage for future AI stages
    priority_labels_count = sum(
        1 for r in records if any("priority" in l.lower() or "severity" in l.lower() or l.lower() in ["p0", "p1", "p2", "p3", "critical", "blocker"] for l in r.get("labels", []))
    )
    component_labels_count = sum(
        1 for r in records if any("area" in l.lower() or "component" in l.lower() or "bug" in l.lower() for l in r.get("labels", []))
    )
    resolution_examples = sum(
        1 for r in records if r.get("state") == "closed" and (r.get("comments_count", 0) > 0 or r.get("linked_pull_requests"))
    )

    percentages = {
        "body_present_pct": round((with_body / total_issues) * 100, 1),
        "labels_present_pct": round((with_labels / total_issues) * 100, 1),
        "comments_present_pct": round((with_comments / total_issues) * 100, 1),
        "assignees_present_pct": round((with_assignees / total_issues) * 100, 1),
        "duplicates_detected_pct": round((with_duplicates / total_issues) * 100, 1),
        "pr_references_pct": round((with_prs / total_issues) * 100, 1),
        "closed_issues_pct": round((closed_issues / total_issues) * 100, 1),
    }

    report = {
        "repository": repository_name,
        "total_issues": total_issues,
        "counts": {
            "body_present": with_body,
            "labels_present": with_labels,
            "comments_present": with_comments,
            "assignees_present": with_assignees,
            "duplicates_detected": with_duplicates,
            "pr_references": with_prs,
            "closed_issues": closed_issues
        },
        "percentages": percentages,
        "ground_truth_coverage": {
            "duplicate_detection": {
                "available": with_duplicates > 0,
                "count": with_duplicates,
                "percentage": percentages["duplicates_detected_pct"],
                "notes": "Explicit duplicate relationships extracted via deterministic pattern matching"
            },
            "severity_classification": {
                "available": priority_labels_count > 0,
                "count": priority_labels_count,
                "percentage": round((priority_labels_count / total_issues) * 100, 1),
                "notes": "Issues with priority/severity tags for supervised classification"
            },
            "root_cause_clustering": {
                "available": component_labels_count > 0,
                "count": component_labels_count,
                "percentage": round((component_labels_count / total_issues) * 100, 1),
                "notes": "Issues tagged with component/area/bug labels"
            },
            "resolution_evidence": {
                "available": resolution_examples > 0,
                "count": resolution_examples,
                "percentage": round((resolution_examples / total_issues) * 100, 1),
                "notes": "Closed issues containing discussion comments or linked PR evidence"
            }
        }
    }

    logger.info("==================================================")
    logger.info(f"  Data Quality & Completeness Report: {repository_name}")
    logger.info("==================================================")
    logger.info(f"  Total Silver Issues:      {total_issues}")
    logger.info(f"  Body Present:             {with_body} ({percentages['body_present_pct']}%)")
    logger.info(f"  Labels Present:           {with_labels} ({percentages['labels_present_pct']}%)")
    logger.info(f"  Comments Present:         {with_comments} ({percentages['comments_present_pct']}%)")
    logger.info(f"  Assignees Present:        {with_assignees} ({percentages['assignees_present_pct']}%)")
    logger.info(f"  Duplicates Detected:      {with_duplicates} ({percentages['duplicates_detected_pct']}%)")
    logger.info(f"  PR References:            {with_prs} ({percentages['pr_references_pct']}%)")
    logger.info(f"  Closed Issues:            {closed_issues} ({percentages['closed_issues_pct']}%)")
    logger.info("--------------------------------------------------")
    logger.info("  AI Ground-Truth Coverage:")
    logger.info(f"    - Duplicates:           {with_duplicates} examples")
    logger.info(f"    - Priority/Severity:    {priority_labels_count} examples")
    logger.info(f"    - Component/Area:       {component_labels_count} examples")
    logger.info(f"    - Resolution Evidence:  {resolution_examples} examples")
    logger.info("==================================================")

    return report

def main():
    parser = argparse.ArgumentParser(description="SupportPilot - Data Quality & Completeness Report")
    parser.add_argument("--owner", type=str, default="microsoft", help="Repository owner (default: microsoft)")
    parser.add_argument("--repo", type=str, default="vscode", help="Repository name (default: vscode)")
    args = parser.parse_args()

    generate_quality_report(owner=args.owner, repo=args.repo)

if __name__ == "__main__":
    main()
