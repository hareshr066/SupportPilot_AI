from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.database.models import Issue, Label, Comment, PullRequest, Repository
from app.evaluation.config import EvaluationConfig

class EvaluationDatasetItem:
    def __init__(
        self,
        ticket_id: int,
        repository_id: int,
        issue_number: int,
        title: str,
        body: str,
        labels: List[str],
        state: str,
        assignees: List[str],
        duplicate_target: Optional[int],
        component: Optional[str],
        resolution_ground_truth: Optional[str],
        linked_pr: Optional[int],
        closing_comment: Optional[str],
        created_at: datetime,
        closed_at: Optional[datetime],
        severity_label: Optional[str] = None
    ):
        self.ticket_id = ticket_id
        self.repository_id = repository_id
        self.issue_number = issue_number
        self.title = title
        self.body = body
        self.labels = labels
        self.state = state
        self.assignees = assignees
        self.duplicate_target = duplicate_target
        self.component = component
        self.resolution_ground_truth = resolution_ground_truth
        self.linked_pr = linked_pr
        self.closing_comment = closing_comment
        self.created_at = created_at
        self.closed_at = closed_at
        self.severity_label = severity_label

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "repository_id": self.repository_id,
            "issue_number": self.issue_number,
            "title": self.title,
            "body": self.body,
            "labels": self.labels,
            "state": self.state,
            "assignees": self.assignees,
            "duplicate_target": self.duplicate_target,
            "component": self.component,
            "resolution_ground_truth": self.resolution_ground_truth,
            "linked_pr": self.linked_pr,
            "closing_comment": self.closing_comment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "severity_label": self.severity_label
        }


class EvaluationDatasetBuilder:
    def __init__(self, config: Optional[EvaluationConfig] = None):
        self.config = config or EvaluationConfig()

    def build_dataset(
        self,
        db_session: Session,
        repository_id: Optional[int] = None
    ) -> List[EvaluationDatasetItem]:
        query = select(Issue).options(
            joinedload(Issue.labels),
            joinedload(Issue.assignees),
            joinedload(Issue.comments),
            joinedload(Issue.pull_requests)
        ).order_by(Issue.created_at.asc())

        if repository_id:
            query = query.where(Issue.repository_id == repository_id)

        issues = db_session.scalars(query).unique().all()
        dataset_items: List[EvaluationDatasetItem] = []

        for issue in issues:
            label_names = [l.name for l in issue.labels]
            assignee_logins = [a.login for a in issue.assignees]
            
            # Extract component label (e.g., "area:terminal", "component:core")
            component = None
            for l_name in label_names:
                l_lower = l_name.lower()
                if l_lower.startswith(("area:", "component:", "subsystem:")):
                    component = l_name.split(":", 1)[1].strip()
                    break

            # Extract severity label (e.g., "severity:high", "p0", "priority:p1")
            severity_label = None
            for l_name in label_names:
                l_lower = l_name.lower()
                if any(kw in l_lower for kw in ["severity", "priority", "critical", "p0", "p1", "p2", "high", "medium", "low"]):
                    severity_label = l_name
                    break

            # Extract closing comment / resolution ground truth
            closing_comment = None
            if issue.comments:
                sorted_comments = sorted(issue.comments, key=lambda c: c.created_at or datetime.min)
                closing_comment = sorted_comments[-1].body if sorted_comments else None

            linked_pr_number = issue.pull_requests[0].pr_number if issue.pull_requests else None
            
            # Resolution ground truth is closing comment or linked PR html_url/number
            res_truth = closing_comment
            if not res_truth and issue.pull_requests:
                res_truth = f"Linked PR #{linked_pr_number}"

            item = EvaluationDatasetItem(
                ticket_id=issue.id,
                repository_id=issue.repository_id,
                issue_number=issue.issue_number,
                title=issue.title,
                body=issue.body or "",
                labels=label_names,
                state=issue.state,
                assignees=assignee_logins,
                duplicate_target=issue.duplicate_of_issue_number,
                component=component,
                resolution_ground_truth=res_truth,
                linked_pr=linked_pr_number,
                closing_comment=closing_comment,
                created_at=issue.created_at,
                closed_at=issue.closed_at,
                severity_label=severity_label
            )
            dataset_items.append(item)

        return dataset_items

    def create_temporal_split(
        self,
        dataset: List[EvaluationDatasetItem]
    ) -> Tuple[List[EvaluationDatasetItem], List[EvaluationDatasetItem], List[EvaluationDatasetItem], Dict[str, Any]]:
        """
        Chronological split: Train (60%), Validation (20%), Test (20%).
        Guarantees zero future-to-past data leakage.
        """
        sorted_dataset = sorted(dataset, key=lambda x: x.created_at)
        total = len(sorted_dataset)

        if total == 0:
            return [], [], [], {
                "train_count": 0, "val_count": 0, "test_count": 0,
                "train_range": None, "val_range": None, "test_range": None
            }

        train_end = int(total * self.config.train_ratio)
        val_end = int(total * (self.config.train_ratio + self.config.val_ratio))

        train_split = sorted_dataset[:train_end]
        val_split = sorted_dataset[train_end:val_end]
        test_split = sorted_dataset[val_end:]

        split_info = {
            "total_count": total,
            "train_count": len(train_split),
            "val_count": len(val_split),
            "test_count": len(test_split),
            "train_range": (train_split[0].created_at.isoformat(), train_split[-1].created_at.isoformat()) if train_split else None,
            "val_range": (val_split[0].created_at.isoformat(), val_split[-1].created_at.isoformat()) if val_split else None,
            "test_range": (test_split[0].created_at.isoformat(), test_split[-1].created_at.isoformat()) if test_split else None,
        }

        return train_split, val_split, test_split, split_info
