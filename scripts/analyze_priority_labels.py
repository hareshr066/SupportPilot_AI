import os
import sys
import argparse
import logging
from typing import Dict, List, Set, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, func
from app.database.session import get_db
from app.database.models import Repository, Issue, Label, issue_labels

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
logger = logging.getLogger("analyze_priority_labels")

DEFAULT_SEVERITY_PATTERNS = [
    "priority", "severity", "critical", "urgent", "blocker",
    "p0", "p1", "p2", "p3", "bug-major", "bug-minor"
]


def analyze_repository_labels(repo_owner: str, repo_name: str) -> Dict[str, Any]:
    """
    Analyzes issues and labels in PostgreSQL database for a specific repository.
    Reports label frequencies and identifies candidate severity/priority labels.
    """
    full_name = f"{repo_owner}/{repo_name}"
    report = {
        "repository": full_name,
        "total_issues": 0,
        "total_labels": 0,
        "label_frequencies": {},
        "label_percentages": {},
        "candidate_severity_labels": [],
        "has_usable_severity_labels": False,
        "reason": ""
    }

    with get_db() as session:
        repo = session.scalar(
            select(Repository).where(Repository.owner == repo_owner, Repository.name == repo_name)
        )
        if not repo:
            report["reason"] = f"Repository '{full_name}' not found in PostgreSQL database."
            return report

        total_issues = session.scalar(
            select(func.count(Issue.id)).where(Issue.repository_id == repo.id)
        ) or 0
        report["total_issues"] = total_issues

        if total_issues == 0:
            report["reason"] = "No issues found in repository."
            return report

        # Fetch label frequencies
        label_stats = session.execute(
            select(Label.name, func.count(issue_labels.c.issue_id))
            .join(issue_labels, Label.id == issue_labels.c.label_id)
            .where(Label.repository_id == repo.id)
            .group_by(Label.name)
        ).all()

        report["total_labels"] = len(label_stats)
        freq_dict = {name: count for name, count in label_stats}
        perc_dict = {name: round((count / total_issues) * 100, 2) for name, count in label_stats}
        report["label_frequencies"] = freq_dict
        report["label_percentages"] = perc_dict

        # Identify candidate severity labels
        candidates = []
        for label_name in freq_dict.keys():
            lower_name = label_name.lower()
            if any(pattern in lower_name for pattern in DEFAULT_SEVERITY_PATTERNS):
                candidates.append(label_name)

        report["candidate_severity_labels"] = candidates

        if not candidates:
            report["has_usable_severity_labels"] = False
            report["reason"] = "No usable severity/priority labels found matching patterns."
        else:
            report["has_usable_severity_labels"] = True

    return report


def main():
    parser = argparse.ArgumentParser(description="Analyze GitHub repository priority and severity labels.")
    parser.add_argument("--owner", type=str, default="microsoft", help="Repository owner")
    parser.add_argument("--repo", type=str, default="vscode", help="Repository name")
    args = parser.parse_args()

    logger.info(f"Analyzing priority and severity labels for {args.owner}/{args.repo}...")
    report = analyze_repository_labels(args.owner, args.repo)

    logger.info("==========================================")
    logger.info("     Severity Label Analysis Report       ")
    logger.info("==========================================")
    logger.info(f"  Repository:                 {report['repository']}")
    logger.info(f"  Total Issues:               {report['total_issues']}")
    logger.info(f"  Total Unique Labels:        {report['total_labels']}")
    logger.info(f"  Candidate Severity Labels:  {report['candidate_severity_labels']}")
    logger.info(f"  Has Usable Severity Labels: {report['has_usable_severity_labels']}")
    if report["reason"]:
        logger.info(f"  Note/Reason:                {report['reason']}")
    logger.info("------------------------------------------")
    logger.info("  All Label Frequencies:")
    if report["label_frequencies"]:
        for name, count in report["label_frequencies"].items():
            perc = report["label_percentages"].get(name, 0.0)
            logger.info(f"    - {name}: {count} issues ({perc}%)")
    else:
        logger.info("    (No labels recorded)")
    logger.info("==========================================")


if __name__ == "__main__":
    main()
