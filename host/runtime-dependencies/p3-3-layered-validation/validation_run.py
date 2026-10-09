"""Thin invocation of the existing P1.4 candidate validator, logic channel only."""
from p33deps import adapter


def run_logic_validation(store, key, task, authority, policy_supplier, port, *, profile=None, clock=None):
    # The predecessor compiles the whole plan, checks authority, fresh policy,
    # budget, observation sessions and every intermediate/final state.
    # No oracle parameters, Android tools, model calls or publication here.
    return adapter.FlowAdapter(enabled=True, profile=profile, clock=clock).validate_candidate(
        store, key, task, authority, policy_supplier, port)
