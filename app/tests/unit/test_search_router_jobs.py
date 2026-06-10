from __future__ import annotations

from server.api.search import router
from server.domain.jobs import JobCancelResponse, JobStartResponse, JobStatusResponse


###############################################################################
def test_jobs_router_wiring_and_response_models() -> None:
    route_map = {
        (route.path, tuple(sorted(route.methods or []))): route
        for route in router.routes
    }
    assert ("/maps/jobs", ("POST",)) in route_map
    assert ("/maps/jobs/{job_id}", ("GET",)) in route_map
    assert ("/maps/jobs/{job_id}", ("DELETE",)) in route_map
    assert route_map[("/maps/jobs", ("POST",))].response_model is JobStartResponse
    assert route_map[("/maps/jobs/{job_id}", ("GET",))].response_model is JobStatusResponse
    assert route_map[("/maps/jobs/{job_id}", ("DELETE",))].response_model is JobCancelResponse
