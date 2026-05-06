"""Tests for 0002_b2b_model ORM model definitions."""
import pytest

from app.leads.models import AssignmentStatus, DealType, Lead, Priority
from app.contacts.models import Contact, ContactRoleType, VerifiedStatus
from app.activity.models import Activity, ActivityType
from app.followups.models import Followup, FollowupStatus, ReminderKind
from app.auth.models import DEFAULT_SCORING_CRITERIA, ScoringCriteria
from app.pipelines.models import DEFAULT_GATE_CRITERIA, DEFAULT_STAGES, Stage


def test_default_stages_count():
    assert len(DEFAULT_STAGES) == 12


def test_default_stages_positions_unique():
    positions = [s["position"] for s in DEFAULT_STAGES]
    assert len(positions) == len(set(positions))


def test_won_lost_stages():
    won = [s for s in DEFAULT_STAGES if s.get("is_won")]
    lost = [s for s in DEFAULT_STAGES if s.get("is_lost")]
    assert len(won) == 1 and len(lost) == 1


def test_gate_criteria_keys():
    assert set(DEFAULT_GATE_CRITERIA.keys()) == set(range(1, 11))


def test_scoring_criteria_count():
    assert len(DEFAULT_SCORING_CRITERIA) == 8


def test_scoring_criteria_weights_sum():
    assert sum(c["weight"] for c in DEFAULT_SCORING_CRITERIA) == 100


def test_deal_type_values():
    assert len(list(DealType)) == 6
    assert DealType.enterprise_direct == "enterprise_direct"


def test_priority_values():
    assert set(p.value for p in Priority) == {"A", "B", "C", "D"}


def test_assignment_status_values():
    assert set(s.value for s in AssignmentStatus) == {"pool", "assigned", "transferred"}


def test_contact_role_type_values():
    expected = {"economic_buyer", "champion", "technical_buyer", "operational_buyer"}
    assert set(r.value for r in ContactRoleType) == expected


def test_activity_type_count():
    assert len(list(ActivityType)) == 9


def test_followup_status_values():
    assert set(s.value for s in FollowupStatus) == {"pending", "active", "done", "overdue"}


def test_reminder_kind_values():
    assert set(k.value for k in ReminderKind) == {"manager", "auto_email", "ai_hint"}


def test_tablenames():
    assert Lead.__tablename__ == "leads"
    assert Contact.__tablename__ == "contacts"
    assert Activity.__tablename__ == "activities"
    assert Followup.__tablename__ == "followups"
    assert ScoringCriteria.__tablename__ == "scoring_criteria"


def test_lead_relationship_attrs():
    assert hasattr(Lead, "contacts")
    assert hasattr(Lead, "activities")
    assert hasattr(Lead, "followups")


def test_verified_status_values():
    assert set(v.value for v in VerifiedStatus) == {"verified", "to_verify"}


def test_gate_criteria_values_are_lists_of_strings():
    for position, criteria in DEFAULT_GATE_CRITERIA.items():
        assert isinstance(criteria, list), f"position {position}: expected list"
        for item in criteria:
            assert isinstance(item, str), f"position {position}: expected str, got {type(item)}"
