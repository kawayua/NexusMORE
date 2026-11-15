"""Local HTTP adapter; all state transitions remain in Workflow."""
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Any, Literal

import psycopg
from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .workflow import Workflow, WorkflowError

Identifier = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
Text = Annotated[str, Field(min_length=1, max_length=2000)]


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ProjectCreate(Body):
    id: Identifier
    title: Text


class TaskCreate(Body):
    id: Identifier
    contract: dict[str, Any]
    executor_key: Literal['historical-fixture', 'manifest-fixture', 'reviewed-run', 'mcp-code-executor', 'pending-code']
    executor_config: dict[str, Any] = Field(default_factory=dict)
    math_package: dict[str, Any] | None = None


class Action(Body):
    actor: Text
    request_id: Identifier
    version: int = Field(ge=1, strict=True)
    kind: Literal['model', 'result', 'revise_model', 'revise_mathematics', 'revise_interpretation', 'restore_version']
    decision: Literal['approve', 'reject'] | None = None
    result_revision: int | None = Field(default=None, ge=1, strict=True)
    defer_execution: bool = Field(default=False, strict=True)
    reason: str = Field(default='', max_length=20000)
    contract: dict[str, Any] | None = None
    source_version: int | None = Field(default=None, ge=1, strict=True)
    claims: dict[str, Any] | None = None
    structured_only: bool = False
    executor_key: Literal['historical-fixture', 'manifest-fixture', 'reviewed-run', 'mcp-code-executor', 'pending-code'] | None = None
    executor_config: dict[str, Any] | None = None
    math_package: dict[str, Any] | None = None
    math_semantic_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def required_action_fields(self):
        if self.kind in ('model', 'result') and self.decision is None:
            raise ValueError('Confirmation requires decision')
        if self.kind in ('result', 'revise_interpretation') and self.result_revision is None:
            raise ValueError('Result action requires result_revision')
        if self.kind == 'revise_model' and self.contract is None:
            raise ValueError('Model revision requires contract')
        if self.kind == 'revise_mathematics' and (self.math_package is None or self.contract is not None):
            raise ValueError('Math revision requires math_package and reuses current contract')
        if self.kind == 'restore_version' and self.source_version is None:
            raise ValueError('Restoration requires source_version')
        if (self.kind.startswith('revise') or self.kind == 'restore_version' or self.decision == 'reject') and not self.reason:
            raise ValueError('Reason or guidance required')
        return self


class HandRecheck(Body):
    rationale: Text


class HandDecision(Body):
    kind: Literal['manuscript','figures']
    decision: Literal['approve','reject']
    actor: Literal['user']
    statement: Text
    reason: Text
    artifact_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    request_id: Identifier


class ModelingRun(Body):
    version: int = Field(ge=1, strict=True)
    actor: Text
    request_id: Identifier
    guidance: str = Field(min_length=1, max_length=20000)
    auto_correct: bool = Field(default=True, strict=True)


class ModelingRecheck(Body):
    version: int = Field(ge=1, strict=True)
    actor: Text
    request_id: Identifier
    rationale: str = Field(min_length=1, max_length=20000)


class MathematicalPublish(Body):
    package: dict[str, Any]
    actor: Text
    request_id: Identifier
    reason: str = Field(min_length=1,max_length=20000)


class SearchFilters(Body):
    doc_id: Identifier | None = None
    case_id: Identifier | None = None
    kind: Literal['paper', 'algorithm', 'problem_statement'] | None = None
    year: int | None = Field(default=None, ge=1900, le=2100, strict=True)


class SearchQuery(Body):
    query: str = Field(min_length=1, max_length=400)
    limit: int = Field(default=5, ge=1, le=20, strict=True)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    score_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    include_same_problem: bool = Field(default=True, strict=True)


class ReferenceRetrieval(Body):
    version: int = Field(ge=1, strict=True)
    tool: Literal['paper_search','web_search','web_read','reference_get','algorithm_search']
    arguments: dict[str, Any]
    actor: Text
    request_id: Identifier


class ReferenceDecision(Body):
    reference_id: str = Field(pattern=r'^ref_[0-9a-f]{64}$')
    decision: Literal['adopted','rejected','considered']


class ReferenceDiscussion(Body):
    version: int = Field(ge=1, strict=True)
    kind: Literal['proposal','feedback']
    text: str = Field(min_length=1,max_length=20000)
    references: list[ReferenceDecision] = Field(min_length=1,max_length=100)
    actor: Text
    request_id: Identifier


@lru_cache(maxsize=1)
def default_retriever():
    from .retrieval import from_config
    return from_config()


def create_app(workflow_factory: Callable = Workflow, retrieval_factory: Callable | None = None) -> FastAPI:
    app = FastAPI(title='ModelCrew local API', version='0.1.0',
                  description='Trusted local API. Actors are audit labels. Confirmation and recovery reuse stage B.')

    def workflow():
        # A connection/checkpointer pair per request; never share sessions across threads.
        with workflow_factory() as instance:
            yield instance

    W = Annotated[Any, Depends(workflow)]

    @app.exception_handler(WorkflowError)
    def workflow_error(request: Request, exc: WorkflowError):
        message = str(exc)
        status = 404 if message in ('Unknown task', 'Unknown project', 'Unknown contract version', 'Unknown assembly run', 'Unknown assembly build') else 409
        return JSONResponse(status_code=status, content={'error': {'code': 'not_found' if status == 404 else 'workflow_conflict', 'message': message}})

    @app.exception_handler(ValueError)
    def invalid_value(request: Request, exc: ValueError):
        status = 404 if str(exc) == 'Unknown contract version' else 422
        return JSONResponse(status_code=status, content={'error': {'code': 'not_found' if status == 404 else 'invalid_request', 'message': str(exc)}})

    @app.exception_handler(psycopg.Error)
    @app.exception_handler(RuntimeError)
    @app.exception_handler(OSError)
    def unavailable(request: Request, exc: Exception):
        # Never expose a connection URL, credentials or backend exception detail.
        return JSONResponse(status_code=503, content={'error': {'code': 'service_unavailable', 'message': 'Database or execution service unavailable; inspect state before retrying.'}})

    from .retrieval import RetrievalUnavailable

    @app.exception_handler(RetrievalUnavailable)
    def retrieval_unavailable(request: Request, exc: RetrievalUnavailable):
        return JSONResponse(status_code=503, content={'error': {'code': 'retrieval_unavailable',
                            'message': 'Retrieval service unavailable; no evidence was retrieved.'}})

    @app.post('/search')
    def search(body: SearchQuery):
        service = (retrieval_factory or default_retriever)()
        return service.search(body.query, limit=body.limit,
                              filters=body.filters.model_dump(exclude_none=True),
                              score_threshold=body.score_threshold,
                              include_same_problem=body.include_same_problem)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'scope': 'http_process', 'stage': 'C'}

    @app.post('/projects')
    def create_project(body: ProjectCreate, w: W):
        return w.create_project(body.id, body.title)

    @app.get('/projects')
    def projects(w: W, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        return w.list_projects(limit=limit, offset=offset)

    @app.get('/projects/{project_id}/tasks')
    def tasks(project_id: str, w: W, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        return w.list_tasks(project_id, limit=limit, offset=offset)

    @app.post('/projects/{project_id}/tasks', status_code=201)
    def create_task(project_id: str, body: TaskCreate, w: W):
        w.require_project(project_id)
        return w.create(body.id, body.contract, project=project_id,
                        executor_key=body.executor_key, executor_config=body.executor_config, math_package=body.math_package)

    @app.get('/tasks/{task_id}')
    def task(task_id: str, w: W):
        return w.inspect(task_id)

    @app.get('/tasks/{task_id}/versions')
    def versions(task_id: str, w: W):
        return w.versions(task_id)

    @app.get('/tasks/{task_id}/versions/{version}')
    def version(task_id: str, version: int, w: W):
        return w.version_dossier(task_id, version)

    @app.get('/tasks/{task_id}/proposal')
    def proposal(task_id: str, w: W):
        state = w.inspect(task_id)
        return {'task_id': task_id, 'contract': state['contract'],
                'model_approved': state['task']['model_approved'],
                'mathematics': state.get('mathematics'),
                'reference_evidence': w.tool_evidence(task_id)}

    @app.post('/tasks/{task_id}/modeling/runs')
    def modeling_run(task_id: str, body: ModelingRun, w: W):
        return w.run_modeling(task_id, **body.model_dump())

    @app.post('/tasks/{task_id}/modeling/{run_id}/recheck')
    def modeling_recheck(task_id: str, run_id: str, body: ModelingRecheck, w: W):
        return w.recheck_modeling(task_id, run_id=run_id, **body.model_dump())

    @app.get('/tasks/{task_id}/modeling')
    def modeling_status(task_id: str, w: W):
        return w.modeling_status(task_id)

    from .assembly_runtime import AssemblyRequest

    @app.post('/projects/{project_id}/assembly-runs')
    def assembly_start(project_id: str, body: AssemblyRequest, w: W):
        return w.start_assembly(project_id, **body.model_dump())

    @app.get('/projects/{project_id}/assembly-runs/{run_id}')
    def assembly_status(project_id: str, run_id: str, w: W):
        return w.assembly_status(project_id, run_id)

    from .assembly_binding import RebindRequest

    @app.post('/projects/{project_id}/assembly-runs/{run_id}/rebindings')
    def assembly_rebind(project_id: str, run_id: str, body: RebindRequest, w: W):
        return w.rebind_assembly(project_id, run_id, **body.model_dump())

    from .assembly_builds import ComposeRequest, Decision as AssemblyDecision, ExportRequest, RenderRequest

    @app.post('/projects/{project_id}/assembly-runs/{run_id}/builds')
    def assembly_compose(project_id: str, run_id: str, body: ComposeRequest, w: W):
        return w.compose_assembly(project_id, run_id, **body.model_dump())

    @app.get('/projects/{project_id}/assembly-builds/{build_id}')
    def assembly_build_status(project_id: str, build_id: str, w: W):
        return w.assembly_build_status(project_id, build_id)

    @app.post('/projects/{project_id}/assembly-builds/{build_id}/decisions')
    def assembly_build_decision(project_id: str, build_id: str, body: AssemblyDecision, w: W):
        return w.assembly_build_decision(project_id, build_id, **body.model_dump())

    from .assembly_builds import ReviewBindingRequest

    @app.post('/projects/{project_id}/assembly-builds/{build_id}/review-bindings')
    def assembly_review_binding(project_id: str, build_id: str, body: ReviewBindingRequest, w: W):
        return w.bind_assembly_reviews(project_id, build_id, **body.model_dump())

    @app.post('/projects/{project_id}/assembly-builds/{build_id}/exports')
    def assembly_export(project_id: str, build_id: str, body: ExportRequest, w: W):
        return w.export_assembly(project_id, build_id, **body.model_dump())

    @app.post('/projects/{project_id}/assembly-builds/{build_id}/renders')
    def assembly_render(project_id: str, build_id: str, body: RenderRequest, w: W):
        return w.render_assembly(project_id, build_id, **body.model_dump())

    from .assembly_w2 import W2Request

    @app.post('/projects/{project_id}/assembly-builds/{build_id}/w2-reviews')
    def assembly_w2_review(project_id: str, build_id: str, body: W2Request, w: W):
        return w.review_assembly_w2(project_id, build_id, **body.model_dump())

    from .assembly_w2 import DeliveryRetry

    @app.post('/projects/{project_id}/assembly-builds/{build_id}/w2-reviews/{review_request_id}/retry-delivery')
    def retry_w2_delivery(project_id: str, build_id: str, review_request_id: str, body: DeliveryRetry, w: W):
        return w.retry_assembly_w2_delivery(project_id, build_id, review_request_id, **body.model_dump())

    @app.post('/projects/{project_id}/assembly-builds/{build_id}/recover')
    def assembly_recover(project_id: str, build_id: str, w: W):
        return w.recover_assembly(project_id, build_id)

    from .hand_runtime import RunRequest

    @app.post('/tasks/{task_id}/hands/{hand}/runs')
    def hand_start(task_id: str, hand: Literal['coding','writing'], body: RunRequest, w: W):
        return w.start_hand(task_id,hand,**body.model_dump())

    @app.get('/tasks/{task_id}/hand-runs/{run_id}')
    def hand_status(task_id: str, run_id: str, w: W):
        return w.hand_status(task_id,run_id)

    @app.post('/tasks/{task_id}/hand-runs/{run_id}/advance')
    def hand_advance(task_id: str, run_id: str, w: W):
        return w.advance_hand(task_id,run_id)

    from .hand_repair import RepairRequest

    @app.post('/tasks/{task_id}/hand-runs/{run_id}/repair')
    def hand_repair(task_id: str, run_id: str, body: RepairRequest, w: W):
        return w.repair_hand(task_id, run_id, **body.model_dump())

    @app.post('/tasks/{task_id}/hand-runs/{run_id}/recheck')
    def hand_recheck(task_id: str,run_id: str,body: HandRecheck,w: W):
        return w.recheck_hand(task_id,run_id,**body.model_dump())

    @app.post('/tasks/{task_id}/hand-runs/{run_id}/decisions')
    def hand_decision(task_id: str, run_id: str, body: HandDecision, w: W):
        return w.hand_decision(task_id,run_id,**body.model_dump())

    @app.get('/tasks/{task_id}/result')
    def result(task_id: str, w: W):
        state = w.inspect(task_id)
        return {'task_id': task_id, 'version': state['task']['current_version'],
                'result': state['result'], 'execution': state['execution'],
                'result_approved': state['task']['result_approved']}

    @app.get('/tasks/{task_id}/artifacts')
    def artifacts(task_id: str, w: W, version: int | None = Query(None, ge=1)):
        dossier = w.version_dossier(task_id, version)
        return {'task_id': task_id, 'version': dossier['version'], 'executions': dossier['executions'],
                'entry_artifacts': [{'entry_id': entry['id'], 'artifacts': entry['body'].get('artifacts', [])}
                                    for entries in dossier['entries'].values() for entry in entries]}

    @app.get('/tasks/{task_id}/versions/{version}/mathematics')
    def mathematical_proposal(task_id: str, version: int, w: W):
        return w.mathematical_proposal(task_id,version)

    @app.post('/tasks/{task_id}/versions/{version}/mathematics')
    def publish_mathematics(task_id: str, version: int, body: MathematicalPublish, w: W):
        return w.publish_mathematics(task_id,version=version,**body.model_dump())

    @app.post('/tasks/{task_id}/actions')
    def action(task_id: str, body: Action, w: W):
        return w.action(task_id, **body.model_dump())

    @app.post('/tasks/{task_id}/resume')
    def resume(task_id: str, w: W):
        return w.resume(task_id)

    @app.post('/tasks/{task_id}/references/retrieve')
    def retrieve_references(task_id: str, body: ReferenceRetrieval, w: W):
        return w.retrieve_references(task_id, **body.model_dump())

    @app.post('/tasks/{task_id}/references/discussions')
    def discuss_references(task_id: str, body: ReferenceDiscussion, w: W):
        return w.discuss_references(task_id, **body.model_dump())

    @app.get('/tasks/{task_id}/tool-evidence')
    def tool_evidence(task_id: str, w: W, version: int | None = Query(None,ge=1)):
        return w.tool_evidence(task_id,version)

    return app


app = create_app()


