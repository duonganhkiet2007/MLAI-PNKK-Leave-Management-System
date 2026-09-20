"""Compatibility facade: one deterministic engine and one day calculator."""
from rule_engine import LeaveRequest as ExtendedLeaveRequest, LeaveRuleEngine, calculate_workdays
from rule_engine import PAID_ENTITLEMENTS as SPECIAL_LEAVE_MAX_DAYS
DecisionTreeEngine = LeaveRuleEngine
decision_tree_engine = LeaveRuleEngine()
