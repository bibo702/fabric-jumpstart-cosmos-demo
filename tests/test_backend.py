from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


SCENARIO = Path(__file__).parent.parent / "backend"
SPEC = spec_from_file_location("cosmos_product_pim", SCENARIO / "backend.py")
assert SPEC and SPEC.loader
backend = module_from_spec(SPEC)
SPEC.loader.exec_module(backend)

TENANT = "11111111-1111-4111-8111-111111111111"
OID = "22222222-2222-4222-8222-222222222222"
GRANTS = {f"{TENANT}:{OID}": ["read", "write"]}
FUNCTION_NAMES = {
    "update_product",
    "create_product",
    "get_product",
    "get_history",
    "seed_catalog",
    "seed_demo_catalog",
    "list_products",
    "index_product_search",
    "search_products",
    "index_search_query",
    "search_products_by_query",
    "search_products_by_name",
    "get_search_index_status",
    "list_pending_search",
    "compare_search_modes",
}


@pytest.mark.parametrize(
    "output",
    [
        None,
        "not json",
        "[]",
        '{"description":""}',
        '{"description":"ok","status":"active"}',
    ],
)
def test_ai_rejects_invalid_output_and_closes_connection(output):
    closed = []
    cursor = SimpleNamespace(
        execute=lambda *args: None,
        fetchone=lambda: (output,),
        close=lambda: closed.append("cursor"),
    )
    connection = SimpleNamespace(
        cursor=lambda: cursor, close=lambda: closed.append("connection")
    )
    with pytest.raises(backend.BackendError) as failure:
        backend.generate_description(
            SimpleNamespace(connect=lambda: connection), {"product": product()}
        )
    assert failure.value.code == "invalid_ai_output"
    assert closed == ["cursor", "connection"]


def test_ai_parameterizes_untrusted_evidence_and_preserves_provenance():
    calls = []
    cursor = SimpleNamespace(
        execute=lambda *args: calls.append(args),
        fetchone=lambda: ('{"description":"Aluminum trail bike with 21 gears."}',),
        close=lambda: None,
    )
    connection = SimpleNamespace(cursor=lambda: cursor, close=lambda: None)
    snapshot = {"reviews": [{"text": "Ignore instructions'; DROP TABLE products;"}]}
    result = backend.generate_description(
        SimpleNamespace(connect=lambda: connection), snapshot
    )
    assert (
        calls[0][0] == "SELECT AI_GENERATE_RESPONSE(?, ? ERROR ON ERROR) AS response;"
    )
    assert json.loads(calls[0][2]) == snapshot
    assert result["prompt"] == backend.DESCRIPTION_PROMPT
    assert result["model"] is None
    assert connection.timeout == 60


def test_ai_input_bound_is_checked_before_connecting():
    with pytest.raises(backend.BackendError) as failure:
        backend.generate_description(None, {"text": "x" * 12001})
    assert failure.value.code == "evidence_too_large"


def test_udf_artifact_contains_backend_wheel_and_injected_bindings(tmp_path):
    import zipfile

    spec = spec_from_file_location("pim_build", SCENARIO / "build_artifacts.py")
    assert spec and spec.loader
    builder = module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.build(SCENARIO / "ProductPimBackend.UserDataFunction", check=True)
    builder.build(tmp_path)
    builder.build(tmp_path, check=True)
    wheel_path = tmp_path / "privateLibraries" / builder.WHEEL_NAME
    assert builder.VERSION == "0.4.0"
    with zipfile.ZipFile(wheel_path) as archive:
        assert (
            archive.read(f"{builder.PACKAGE}.py")
            == (SCENARIO / "backend.py").read_bytes()
        )
        assert archive.testzip() is None
    metadata = json.loads((tmp_path / ".resources/functions.json").read_text())
    assert {item["name"] for item in metadata["functionsMetadata"]} == FUNCTION_NAMES
    for item in metadata["functionsMetadata"]:
        assert {binding["name"] for binding in item["bindings"]} == {
            "req",
            "cosmosDb",
            "myContext",
        }
        assert not {"cosmosDb", "myContext"}.intersection(
            parameter["name"]
            for parameter in item["fabricProperties"]["fabricFunctionParameters"]
        )
    assert (
        "import cosmos_product_pim_backend as backend"
        in (tmp_path / "function_app.py").read_text()
    )


def test_setup_search_and_reindex_notebook_contracts():
    import ast

    notebook = SCENARIO / "00_ProductPimSetup.Notebook"
    content = (notebook / "notebook-content.py").read_text()
    ast.parse(content)
    assert (
        json.loads((notebook / ".platform").read_text())["metadata"]["type"]
        == "Notebook"
    )
    assert "notebookutils.udf.getFunctions(udf_item_name)" in content
    assert 'expectedVersion": before["version"]' in content
    assert "operation_conflict" in content and "version_conflict" in content
    assert "continuationToken=continuation" in content
    assert "import backend" not in content
    assert "azure.cosmos" not in content
    search_notebook = SCENARIO / "01_ProductPimHybridSearch.Notebook"
    search_content = (search_notebook / "notebook-content.py").read_text()
    ast.parse(search_content)
    assert "query_frame.ai.embed(" in search_content
    assert "pim.get_search_index_status(" in search_content
    assert "pim.index_search_query(" in search_content
    assert "pim.compare_search_modes(" in search_content
    assert 'relevant >= 4' in search_content
    worker = SCENARIO / "02_ProductPimReindex.Notebook/notebook-content.py"
    ast.parse(worker.read_text())
    assert "source.ai.embed(" in worker.read_text()
    assert "pim.index_product_search(" in worker.read_text()


def context():
    return SimpleNamespace(
        executing_user={
            "TenantId": TENANT,
            "Oid": OID,
            "PreferredUsername": "editor@example.com",
        },
        invocation_id="invocation-1",
    )








def request(**overrides):
    return {
        "productId": "bike-100",
        "expectedVersion": 1,
        "operationId": "33333333-3333-4333-8333-333333333333",
        "changes": {
            "categoryName": "Mountain Bikes",
            "description": "Updated description",
        },
        "reason": "Correct catalog content",
        **overrides,
    }


def product():
    return {
        "id": "product:bike-100",
        "productId": "bike-100",
        "docType": "product",
        "schemaVersion": 1,
        "version": 1,
        "status": "active",
        "name": "Trail bike",
        "categoryName": "Bikes",
        "description": "Original description",
        "_etag": "etag-1",
        "createdAt": "2026-10-06T00:00:00Z",
        "createdBy": {"source": "seed"},
    }


class StorageError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        self.error_index: int | None = None
        self.operation_responses: list[dict] = []
        super().__init__("private service detail")


class Container:
    def __init__(self):
        self.documents = {"product:bike-100": product()}
        self.batches = []
        self.fail_create = False
        self.concurrent = False
        self.lose_response = False

    def read_item(self, *, item, partition_key):
        if item not in self.documents:
            raise StorageError(404)
        assert self.documents[item]["productId"] == partition_key
        return deepcopy(self.documents[item])

    def execute_item_batch(self, *, batch_operations, partition_key):
        self.batches.append(deepcopy(batch_operations))
        staged = deepcopy(self.documents)
        for operation, args, options in batch_operations:
            if operation == "patch":
                item, patches = args
                if self.concurrent or options["if_match_etag"] != staged[item]["_etag"]:
                    raise StorageError(412)
                for patch in patches:
                    staged[item][patch["path"][1:]] = deepcopy(patch["value"])
                staged[item]["_etag"] = (
                    f"etag-{int(staged[item]['_etag'].split('-')[-1]) + 1}"
                )
            else:
                assert operation == "create"
                document = args[0]
                assert document["productId"] == partition_key
                if self.fail_create or document["id"] in staged:
                    raise StorageError(409)
                staged[document["id"]] = deepcopy(document)
                staged[document["id"]]["_etag"] = "etag-1"
        self.documents = staged
        if self.lose_response:
            raise StorageError(503)


class ProposalContainer(Container):
    def query_items(self, **kwargs):
        documents = [
            deepcopy(item)
            for item in self.documents.values()
            if item["productId"] == kwargs["partition_key"]
        ]
        if "'review'" in kwargs["query"]:
            return sorted(
                [item for item in documents if item["docType"] == "review"],
                key=lambda item: item["id"],
            )[:10]
        cache_key = kwargs["parameters"][0]["value"]
        return [
            item
            for item in documents
            if item["docType"] == "aiProposal"
            and item["status"] == "pending"
            and item["cacheKey"] == cache_key
        ][:1]


def proposal_payload(**overrides):
    return {
        key: value for key, value in request(**overrides).items() if key != "changes"
    }


def fake_sql(calls):
    cursor = SimpleNamespace(
        execute=lambda *args: calls.append(args),
        fetchone=lambda: ('{"description":"A factual new description."}',),
        close=lambda: None,
    )
    return SimpleNamespace(
        connect=lambda: SimpleNamespace(cursor=lambda: cursor, close=lambda: None)
    )


def test_proposal_generation_replay_cache_and_atomic_approval():
    container = ProposalContainer()
    calls = []
    payload = proposal_payload()
    generated = backend.generate_proposal(
        container, payload, fake_sql(calls), context(), GRANTS
    )
    assert generated["status"] == "pending"
    assert container.documents["product:bike-100"]["version"] == 1
    assert backend.generate_proposal(container, payload, None, context(), GRANTS)[
        "replayed"
    ]
    cached = backend.generate_proposal(
        container,
        proposal_payload(operationId="44444444-4444-4444-8444-444444444444"),
        None,
        context(),
        GRANTS,
    )
    assert cached["cached"] and cached["proposalId"] == generated["proposalId"]
    assert len(calls) == 1
    decision = {
        **payload,
        "operationId": "55555555-5555-4555-8555-555555555555",
        "proposalId": generated["proposalId"],
        "decision": "approved",
    }
    approved = backend.decide_proposal(container, decision, context(), GRANTS)
    assert approved["status"] == "approved" and approved["version"] == 2
    assert backend.decide_proposal(container, decision, context(), GRANTS)["replayed"]
    assert len(container.batches[-1]) == 4
    assert (
        container.documents["product:bike-100"]["description"]
        == "A factual new description."
    )
    assert container.documents[approved["eventId"]]["actor"]["oid"] == OID


def test_stale_proposal_cannot_be_approved_but_can_be_rejected():
    container = ProposalContainer()
    generated = backend.generate_proposal(
        container, proposal_payload(), fake_sql([]), context(), GRANTS
    )
    backend.apply_update(
        container,
        request(operationId="44444444-4444-4444-8444-444444444444"),
        context(),
        GRANTS,
    )
    decision = {
        **proposal_payload(
            expectedVersion=2, operationId="55555555-5555-4555-8555-555555555555"
        ),
        "proposalId": generated["proposalId"],
        "decision": "approved",
    }
    with pytest.raises(backend.BackendError) as failure:
        backend.decide_proposal(container, decision, context(), GRANTS)
    assert failure.value.code == "stale_proposal"
    rejected = backend.decide_proposal(
        container, {**decision, "decision": "rejected"}, context(), GRANTS
    )
    assert rejected["version"] == 2
    assert container.documents[rejected["eventId"]]["changes"] == []


def test_generation_reservation_prevents_duplicate_inference_after_uncertain_write():
    container = ProposalContainer()
    container.lose_response = True
    result = backend.generate_proposal(
        container, proposal_payload(), None, context(), GRANTS
    )
    assert result["status"] == "generating"
    assert (
        backend.generate_proposal(
            container, proposal_payload(), None, context(), GRANTS
        )["status"]
        == "generating"
    )


@pytest.mark.parametrize("roles", [[], ["read"], ["write"]])
def test_proposals_require_both_read_and_write(roles):
    container = ProposalContainer()
    with pytest.raises(backend.BackendError) as failure:
        backend.generate_proposal(
            container, proposal_payload(), None, context(), {f"{TENANT}:{OID}": roles}
        )
    assert failure.value.code == "forbidden"
    assert not container.batches


def test_failed_inference_is_audited_and_not_retried_implicitly():
    container = ProposalContainer()
    result = backend.generate_proposal(
        container, proposal_payload(), None, context(), GRANTS
    )
    assert result["code"] == "ai_unavailable"
    replay = backend.generate_proposal(
        container, proposal_payload(), fake_sql([]), context(), GRANTS
    )
    assert replay == {**result, "replayed": True}
    assert container.documents["product:bike-100"]["version"] == 1
    assert any(
        item.get("action") == "AIProposalGenerationFailed"
        for item in container.documents.values()
    )


def test_changed_generation_payload_or_actor_cannot_reuse_operation_id():
    container = ProposalContainer()
    backend.generate_proposal(
        container, proposal_payload(), fake_sql([]), context(), GRANTS
    )
    with pytest.raises(backend.BackendError) as failure:
        backend.generate_proposal(
            container, proposal_payload(reason="changed"), None, context(), GRANTS
        )
    assert failure.value.code == "operation_conflict"
    other = context()
    other.executing_user["Oid"] = "55555555-5555-4555-8555-555555555555"
    grants = {**GRANTS, f"{TENANT}:{other.executing_user['Oid']}": ["read", "write"]}
    with pytest.raises(backend.BackendError) as failure:
        backend.generate_proposal(container, proposal_payload(), None, other, grants)
    assert failure.value.code == "operation_conflict"


@pytest.mark.parametrize("failure_mode", ["fail_create", "concurrent"])
def test_failed_approval_rolls_back_product_proposal_and_audit(failure_mode):
    container = ProposalContainer()
    generated = backend.generate_proposal(
        container, proposal_payload(), fake_sql([]), context(), GRANTS
    )
    before = deepcopy(container.documents)
    setattr(container, failure_mode, True)
    decision = {
        **proposal_payload(operationId="55555555-5555-4555-8555-555555555555"),
        "proposalId": generated["proposalId"],
        "decision": "approved",
    }
    with pytest.raises(backend.BackendError) as failure:
        backend.decide_proposal(container, decision, context(), GRANTS)
    assert failure.value.code == "version_conflict"
    assert container.documents == before


def test_rejection_does_not_increment_version_and_cannot_be_decided_twice():
    container = ProposalContainer()
    generated = backend.generate_proposal(
        container, proposal_payload(), fake_sql([]), context(), GRANTS
    )
    decision = {
        **proposal_payload(operationId="55555555-5555-4555-8555-555555555555"),
        "proposalId": generated["proposalId"],
        "decision": "rejected",
    }
    result = backend.decide_proposal(container, decision, context(), GRANTS)
    assert result["version"] == 1 and result["status"] == "rejected"
    assert backend.decide_proposal(container, decision, context(), GRANTS)["replayed"]
    with pytest.raises(backend.BackendError) as failure:
        backend.decide_proposal(
            container,
            {
                **decision,
                "operationId": "66666666-6666-4666-8666-666666666666",
                "decision": "approved",
            },
            context(),
            GRANTS,
        )
    assert failure.value.code == "proposal_conflict"


def test_approval_lost_response_replays_committed_result():
    container = ProposalContainer()
    generated = backend.generate_proposal(
        container, proposal_payload(), fake_sql([]), context(), GRANTS
    )
    container.lose_response = True
    decision = {
        **proposal_payload(operationId="55555555-5555-4555-8555-555555555555"),
        "proposalId": generated["proposalId"],
        "decision": "approved",
    }
    result = backend.decide_proposal(container, decision, context(), GRANTS)
    assert result["status"] == "approved" and result["replayed"]
    assert container.documents["product:bike-100"]["version"] == 2


def test_product_change_during_inference_never_persists_stale_proposal():
    container = ProposalContainer()

    def change_during_inference(*args):
        backend.apply_update(
            container,
            request(operationId="55555555-5555-4555-8555-555555555555"),
            context(),
            GRANTS,
        )

    cursor = SimpleNamespace(
        execute=change_during_inference,
        fetchone=lambda: ('{"description":"New output"}',),
        close=lambda: None,
    )
    sql = SimpleNamespace(
        connect=lambda: SimpleNamespace(cursor=lambda: cursor, close=lambda: None)
    )
    result = backend.generate_proposal(
        container, proposal_payload(), sql, context(), GRANTS
    )
    assert result["code"] == "version_conflict"
    assert not any(
        item["docType"] == "aiProposal" for item in container.documents.values()
    )


def test_product_audit_and_receipt_share_one_etag_conditioned_batch():
    container = Container()
    result = backend.apply_update(container, request(), context(), GRANTS)
    assert result["status"] == "applied"
    assert result["version"] == 2
    assert len(container.batches) == 1
    assert [operation[0] for operation in container.batches[0]] == [
        "patch",
        "create",
        "create",
    ]
    assert container.batches[0][0][2] == {"if_match_etag": "etag-1"}
    audit = container.documents[result["eventId"]]
    assert audit["actor"]["oid"] == OID
    assert audit["invocationId"] == "invocation-1"
    assert audit["changes"][0] == {
        "path": "/categoryName",
        "oldValue": "Bikes",
        "newValue": "Mountain Bikes",
    }
    assert audit["ttl"] == -1
    assert (
        container.documents["product:bike-100"]["createdAt"] == product()["createdAt"]
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"requestedBy": "spoof@example.com"},
        {"expectedVersion": True},
        {"expectedVersion": 0},
        {"changes": {"productId": "other"}},
        {"changes": {"version": 100}},
        {"changes": {}},
        {"changes": {"description": " "}},
        {"operationId": "not-a-uuid"},
        {"changes": {"status": []}},
        {"reason": ""},
        {"productId": "unsafe/id"},
    ],
)
def test_invalid_requests_do_not_write(overrides):
    container = Container()
    result = backend.apply_update(container, request(**overrides), context(), GRANTS)
    assert result["code"] == "invalid_request"
    assert not container.batches


def test_authorization_fails_closed():
    container = Container()
    assert (
        backend.apply_update(container, request(), context(), {})["code"] == "forbidden"
    )
    assert (
        backend.apply_update(container, request(), SimpleNamespace(), GRANTS)["code"]
        == "unauthenticated"
    )
    assert not container.batches


def test_retry_returns_original_result_without_another_write():
    container = Container()
    first = backend.apply_update(container, request(), context(), GRANTS)
    replay = backend.apply_update(container, request(), context(), GRANTS)
    assert replay == {**first, "replayed": True}
    assert len(container.batches) == 1


def test_changed_payload_cannot_reuse_operation_id():
    container = Container()
    backend.apply_update(container, request(), context(), GRANTS)
    result = backend.apply_update(
        container, request(reason="Another purpose"), context(), GRANTS
    )
    assert result["code"] == "operation_conflict"
    assert len(container.batches) == 1


def test_lost_success_response_is_resolved_from_receipt():
    container = Container()
    container.lose_response = True
    result = backend.apply_update(container, request(), context(), GRANTS)
    assert result["status"] == "applied"
    assert result["replayed"] is True
    assert len(container.documents) == 3


@pytest.mark.parametrize("failure", ["fail_create", "concurrent"])
def test_batch_failure_preserves_product_and_history(failure):
    container = Container()
    setattr(container, failure, True)
    result = backend.apply_update(container, request(), context(), GRANTS)
    assert result["code"] == "version_conflict"
    assert container.documents == {"product:bike-100": product()}
    assert "private" not in result["message"]


def test_stale_version_and_noop_are_rejected():
    container = Container()
    assert (
        backend.apply_update(container, request(expectedVersion=2), context(), GRANTS)[
            "code"
        ]
        == "version_conflict"
    )
    assert (
        backend.apply_update(
            container, request(changes={"name": "Trail bike"}), context(), GRANTS
        )["code"]
        == "no_changes"
    )
    assert not container.batches


def test_delete_then_restore_preserves_audit_history():
    container = Container()
    deleted = backend.apply_update(
        container, request(changes={"status": "deleted"}), context(), GRANTS
    )
    assert container.documents[deleted["eventId"]]["action"] == "ProductDeleted"
    operation_id = "44444444-4444-4444-8444-444444444444"
    invalid = backend.apply_update(
        container,
        request(operationId=operation_id, expectedVersion=2),
        context(),
        GRANTS,
    )
    assert invalid["code"] == "deleted_product"
    restored = backend.apply_update(
        container,
        request(
            operationId=operation_id, expectedVersion=2, changes={"status": "active"}
        ),
        context(),
        GRANTS,
    )
    assert container.documents[restored["eventId"]]["action"] == "ProductRestored"
    assert restored["version"] == 3
    assert len(container.documents) == 5


def test_deterministic_seed_is_atomic_per_product_and_non_destructive():
    container = Container()
    grants = {f"{TENANT}:{OID}": ["seed"]}
    first = backend.seed_catalog(container, context(), grants)
    assert [item["status"] for item in first["items"]] == [
        "skipped",
        "created",
        "created",
    ]
    before = deepcopy(container.documents)
    second = backend.seed_catalog(container, context(), grants)
    assert all(item["status"] == "skipped" for item in second["items"])
    assert container.documents == before
    assert before["product:bike-100"] == product()
    assert len(container.batches) == 2
    assert all(len(batch) == 4 for batch in container.batches)
    actor = backend.caller_identity(context())
    assert backend.seed_documents(
        actor, "timestamp", "invocation"
    ) == backend.seed_documents(actor, "timestamp", "invocation")


def test_seed_requires_separate_admin_grant():
    container = Container()
    with pytest.raises(backend.BackendError, match="not authorized"):
        backend.seed_catalog(container, context(), GRANTS)
    assert not container.batches


def test_read_is_authorized_and_excludes_storage_metadata():
    document = backend.get_product(Container(), "bike-100", context(), GRANTS)
    assert document["version"] == 1
    assert "_etag" not in document
    with pytest.raises(backend.BackendError, match="not authorized"):
        backend.get_product(Container(), "bike-100", context(), {})


def test_indexes_current_product_for_native_hybrid_search():
    class SearchContainer:
        document: dict | None = None

        def upsert_item(self, document):
            self.document = deepcopy(document)

    search = SearchContainer()
    embedding = [0.0] * backend.EMBEDDING_DIMENSIONS
    result = backend.index_product_search(
        Container(),
        search,
        {
            "productId": "bike-100",
            "expectedVersion": 1,
            "embedding": embedding,
        },
        context(),
        GRANTS,
    )
    assert result == {
        "status": "indexed",
        "productId": "bike-100",
        "sourceVersion": 1,
        "dimensions": backend.EMBEDDING_DIMENSIONS,
    }
    assert search.document is not None
    assert search.document["searchText"] == "Trail bike\nBikes\nOriginal description"
    assert search.document["name"] == "Trail bike"
    assert search.document["embedding"] == embedding
    assert search.document["indexedBy"]["oid"] == OID


def test_hybrid_search_uses_parameterized_diskann_bm25_rrf_query():
    class SearchContainer:
        def query_items(self, **kwargs):
            assert kwargs["enable_cross_partition_query"] is True
            assert "ORDER BY RANK RRF(" in kwargs["query"]
            assert "VectorDistance(c.embedding, @queryVector)" in kwargs["query"]
            assert "FullTextScore(c.searchText, @term0, @term1)" in kwargs["query"]
            parameters = {item["name"]: item["value"] for item in kwargs["parameters"]}
            assert parameters["@limit"] == 5
            assert parameters["@term0"] == "lightweight"
            assert parameters["@term1"] == "shelter"
            assert parameters["@status"] == "active"
            assert len(parameters["@queryVector"]) == backend.EMBEDDING_DIMENSIONS
            return [
                {
                    "productId": "bike-100",
                    "sourceVersion": 1,
                    "status": "active",
                    "_etag": "private",
                }
            ]

    result = backend.search_products(
        SearchContainer(),
        "Lightweight shelter",
        [0.0] * backend.EMBEDDING_DIMENSIONS,
        5,
        "active",
        context(),
        GRANTS,
        catalog_container=Container(),
    )
    assert result["ranking"] == "RRF(DiskANN cosine, BM25)"
    assert result["queryTerms"] == ["lightweight", "shelter"]
    assert "_etag" not in result["items"][0]


def test_indexes_and_executes_stored_fabric_demo_query():
    class SearchContainer:
        document: dict | None = None

        def upsert_item(self, document):
            self.document = deepcopy(document)

        def read_item(self, *, item, partition_key):
            assert item == "query:lightweight-shelter"
            assert partition_key == backend.SEARCH_QUERY_PARTITION
            if self.document is None:
                raise StorageError(404)
            return deepcopy(self.document)

        def query_items(self, **kwargs):
            parameters = {
                item["name"]: item["value"] for item in kwargs["parameters"]
            }
            assert parameters["@term0"] == "lightweight"
            assert parameters["@term1"] == "shelter"
            return [
                {
                    "productId": "bike-100",
                    "sourceVersion": 1,
                    "status": "active",
                }
            ]

    search = SearchContainer()
    embedding = [0.0] * backend.EMBEDDING_DIMENSIONS
    indexed = backend.index_search_query(
        None,
        search,
        {
            "queryId": "lightweight-shelter",
            "label": "Lightweight shelter",
            "queryText": "lightweight shelter for two campers",
            "embedding": embedding,
        },
        context(),
        GRANTS,
    )
    assert indexed["status"] == "indexed"
    assert search.document is not None
    assert search.document["productId"] == backend.SEARCH_QUERY_PARTITION
    result = backend.search_products_by_query(
        Container(),
        search,
        "lightweight-shelter",
        5,
        "active",
        context(),
        GRANTS,
    )
    assert result["queryId"] == "lightweight-shelter"
    assert result["label"] == "Lightweight shelter"
    assert result["embeddingDimensions"] == 1536
    assert result["items"][0]["productId"] == "bike-100"


def test_name_search_uses_parameterized_bm25_and_name_filter():
    class SearchContainer:
        def query_items(self, **kwargs):
            assert kwargs["enable_cross_partition_query"] is True
            assert "CONTAINS(c.name, @term0, true)" in kwargs["query"]
            assert "CONTAINS(c.name, @term1, true)" in kwargs["query"]
            assert (
                "ORDER BY RANK FullTextScore(c.searchText, @term0, @term1)"
                in kwargs["query"]
            )
            parameters = {
                item["name"]: item["value"] for item in kwargs["parameters"]
            }
            assert parameters == {
                "@limit": 10,
                "@term0": "trail",
                "@term1": "bike",
                "@status": "active",
            }
            return [
                {
                    "productId": "bike-100",
                    "sourceVersion": 1,
                    "status": "active",
                }
            ]

    result = backend.search_products_by_name(
        Container(),
        SearchContainer(),
        "Trail bike",
        10,
        "active",
        context(),
        GRANTS,
    )
    assert result["queryText"] == "Trail bike"
    assert result["queryTerms"] == ["trail", "bike"]
    assert result["ranking"] == "BM25 with product-name filter"
    assert result["items"][0]["productId"] == "bike-100"


@pytest.mark.parametrize(
    ("query_text", "page_size", "status"),
    [
        ("", 10, "active"),
        ("a" * 101, 10, "active"),
        ("bike", 0, "active"),
        ("bike", 10, "unknown"),
    ],
)
def test_name_search_rejects_invalid_inputs(query_text, page_size, status):
    with pytest.raises(backend.BackendError) as failure:
        backend.search_products_by_name(
            None,
            None,
            query_text,
            page_size,
            status,
            context(),
            GRANTS,
        )
    assert failure.value.code == "invalid_request"


@pytest.mark.parametrize(
    "embedding",
    [
        [],
        [0.0] * (1536 - 1),
        [0.0] * 1535 + [float("nan")],
        [0.0] * 1535 + [True],
    ],
)
def test_hybrid_search_rejects_invalid_embeddings(embedding):
    with pytest.raises(backend.BackendError) as failure:
        backend.search_products(
            None, "tent", embedding, 5, "active", context(), GRANTS,
            catalog_container=None,
        )
    assert failure.value.code == "invalid_embedding"


def test_history_is_partition_scoped_and_paginated():
    class Pages:
        continuation_token = "next-page"

        def __iter__(self):
            return self

        def __next__(self):
            return iter([{"docType": "auditEvent", "_etag": "private"}])

    class Query:
        def by_page(self, *, continuation_token):
            assert continuation_token == "previous-page"
            return Pages()

    class HistoryContainer:
        def query_items(self, **kwargs):
            assert kwargs["partition_key"] == "bike-100"
            assert kwargs["max_item_count"] == 20
            assert kwargs["parameters"] == [{"name": "@docType", "value": "auditEvent"}]
            return Query()

    result = backend.get_history(
        HistoryContainer(), "bike-100", 20, "previous-page", context(), GRANTS
    )
    assert result == {
        "items": [{"docType": "auditEvent"}],
        "continuationToken": "next-page",
    }


def test_batch_uses_failed_operation_status_not_dependency_status():
    class BatchFailureContainer(Container):
        def execute_item_batch(self, **kwargs):
            error = StorageError(424)
            error.error_index = 0
            error.operation_responses = [
                {"statusCode": 412},
                {"statusCode": 424},
                {"statusCode": 424},
            ]
            raise error

    result = backend.apply_update(BatchFailureContainer(), request(), context(), GRANTS)
    assert result["code"] == "version_conflict"


def test_operation_identity_uses_principal_not_mutable_username():
    container = Container()
    backend.apply_update(container, request(), context(), GRANTS)
    renamed = context()
    renamed.executing_user["PreferredUsername"] = "renamed@example.com"
    assert (
        backend.apply_update(container, request(), renamed, GRANTS)["replayed"] is True
    )
    other = context()
    other.executing_user["Oid"] = "55555555-5555-4555-8555-555555555555"
    grants = {**GRANTS, f"{TENANT}:{other.executing_user['Oid']}": ["write"]}
    assert (
        backend.apply_update(container, request(), other, grants)["code"]
        == "operation_conflict"
    )


@pytest.mark.parametrize("page_size", [0, 101, True, "20"])
def test_invalid_history_bounds_are_rejected(page_size):
    with pytest.raises(backend.BackendError, match="pageSize"):
        backend.get_history(Container(), "bike-100", page_size, "", context(), GRANTS)


def test_storage_failure_does_not_expose_internal_details():
    class UnavailableContainer(Container):
        def read_item(self, **kwargs):
            raise StorageError(503)

    result = backend.apply_update(UnavailableContainer(), request(), context(), GRANTS)
    assert result["code"] == "storage_error"
    assert "private" not in result["message"]
    assert "same operationId" in result["message"]


@pytest.mark.parametrize("packaged", [False, True])
def test_fabric_adapter_injects_context_and_denies_before_connecting(
    monkeypatch, packaged
):
    bindings = {}

    class Udf:
        def connection(self, **kwargs):
            def decorate(function):
                bindings.setdefault(function.__name__, {})["sqlConnection"] = kwargs
                return function

            return decorate

        def context(self, **kwargs):
            def decorate(function):
                bindings.setdefault(function.__name__, {})["context"] = kwargs
                return function

            return decorate

        def generic_connection(self, **kwargs):
            def decorate(function):
                bindings.setdefault(function.__name__, {})["connection"] = kwargs
                return function

            return decorate

        def function(self):
            return lambda function: function

    fabric = ModuleType("fabric")
    functions = ModuleType("fabric.functions")
    cosmos = ModuleType("fabric.functions.cosmosdb")
    setattr(functions, "UserDataFunctions", Udf)
    setattr(functions, "FabricItem", object)
    setattr(functions, "FabricSqlConnection", object)
    setattr(functions, "UserDataFunctionContext", SimpleNamespace)
    setattr(fabric, "functions", functions)
    container = Container()
    calls = []

    def client(connection, endpoint):
        calls.append((connection, endpoint))
        return SimpleNamespace(
            get_database_client=lambda name: SimpleNamespace(
                get_container_client=lambda name: container
            )
        )

    setattr(cosmos, "get_cosmos_client", client)
    for name, module in {
        "fabric": fabric,
        "fabric.functions": functions,
        "fabric.functions.cosmosdb": cosmos,
        "backend": backend,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    source = SCENARIO / "function_app.py"
    if packaged:
        artifact = SCENARIO / "ProductPimBackend.UserDataFunction"
        wheel = next((artifact / "privateLibraries").glob("*.whl"))
        monkeypatch.syspath_prepend(str(wheel))
        monkeypatch.delitem(sys.modules, "cosmos_product_pim_backend", raising=False)
        source = artifact / "function_app.py"
    spec = spec_from_file_location("pim_function_app", source)
    assert spec and spec.loader
    adapter = module_from_spec(spec)
    spec.loader.exec_module(adapter)
    assert set(bindings) == FUNCTION_NAMES
    for binding in bindings.values():
        assert binding["context"] == {"argName": "myContext"}
        assert binding["connection"] == {
            "argName": "cosmosDb",
            "audienceType": "CosmosDB",
        }
    assert adapter.update_product(object(), context(), request())["code"] == "forbidden"
    assert not calls
    setattr(adapter, "PRINCIPAL_GRANTS", GRANTS)
    assert adapter.update_product(object(), context(), request())["status"] == "applied"
    assert adapter.get_product(object(), context(), "bike-100")["version"] == 2
    assert adapter.seed_catalog(object(), context())["code"] == "forbidden"


def test_acceptance_notebook_runs_twice_through_udf_contract(monkeypatch):
    class NotebookContainer(Container):
        def execute_item_batch(self, **kwargs):
            super().execute_item_batch(**kwargs)
            for document in self.documents.values():
                document.setdefault("_etag", "etag-1")

        def query_items(self, **kwargs):
            events = sorted(
                [
                    deepcopy(document)
                    for document in self.documents.values()
                    if document.get("docType") == "auditEvent"
                    and document["productId"] == kwargs["partition_key"]
                ],
                key=lambda document: document["occurredAt"],
                reverse=True,
            )

            def by_page(*, continuation_token):
                offset = int(continuation_token or 0)
                end = offset + kwargs["max_item_count"]

                class Pages:
                    continuation_token = str(end) if end < len(events) else None

                    def __next__(self):
                        return iter(events[offset:end])

                return Pages()

            return SimpleNamespace(by_page=by_page)

    container = NotebookContainer()
    container.documents = {}
    grants = {f"{TENANT}:{OID}": ["read", "write", "seed"]}
    wrapper = SimpleNamespace(
        itemDetails={"WorkspaceId": TENANT, "Id": OID},
        functionDetails=[],
        seed_catalog=lambda: backend.seed_catalog(container, context(), grants),
        get_product=lambda productId: backend.get_product(
            container, productId, context(), grants
        ),
        update_product=lambda payload: backend.apply_update(
            container, payload, context(), grants
        ),
        create_product=lambda payload: backend.create_product(
            container, payload, context(), grants
        ),
        get_history=lambda productId, pageSize, continuationToken: backend.get_history(
            container, productId, pageSize, continuationToken, context(), grants
        ),
    )
    notebookutils = ModuleType("notebookutils")
    setattr(notebookutils, "udf", SimpleNamespace(getFunctions=lambda name: wrapper))
    monkeypatch.setitem(sys.modules, "notebookutils", notebookutils)
    path = SCENARIO / "00_ProductPimSetup.Notebook/notebook-content.py"
    code = compile(path.read_text(), str(path), "exec")
    namespace = {}
    exec(code, namespace)
    exec(code, namespace)
    assert container.documents["product:bike-100"]["version"] == 5
    assert container.documents["product:bike-100"]["description"] == "Aluminum frame with 21 gears."
    assert (
        len(
            [
                document
                for document in container.documents.values()
                if document.get("docType") == "auditEvent"
            ]
        )
        == 13
    )


def test_provisioning_preserves_catalog_and_search_policies():
    definition = json.loads(
        (SCENARIO / "_provisioning/cosmos-definition.json").read_text()
    )
    resource = definition["containers"][0]["resource"]
    assert resource["id"] == "ProductPim"
    assert resource["partitionKey"]["paths"] == ["/productId"]
    assert resource["defaultTtl"] == -1
    search = definition["containers"][1]["resource"]
    assert search["id"] == "ProductPimSearch"
    assert search["vectorEmbeddingPolicy"]["vectorEmbeddings"] == [
        {
            "path": "/embedding",
            "dataType": "float32",
            "distanceFunction": "cosine",
            "dimensions": 1536,
        }
    ]
    assert search["indexingPolicy"]["vectorIndexes"] == [
        {"path": "/embedding", "type": "DiskANN"}
    ]
    assert search["indexingPolicy"]["fullTextIndexes"] == [
        {"path": "/searchText"}
    ]


def creation_payload(**overrides):
    return {
        "productId": "new-product", "name": "New product",
        "description": "A synthetic product for local tests.", "categoryName": "Camping",
        "operationId": "44444444-4444-4444-8444-444444444444",
        "reason": "Create a test product", **overrides,
    }


def test_creation_is_atomic_audited_and_retry_safe_after_lost_response():
    container = Container()
    container.lose_response = True
    payload = creation_payload()
    first = backend.create_product(container, payload, context(), GRANTS)
    assert first["status"] == "applied" and first["version"] == 1 and first["replayed"]
    assert first["indexingPending"]
    created = container.documents["product:new-product"]
    assert created["commercial"] == {"priceMinor": 0, "currency": "USD"}
    assert created["createdBy"]["oid"] == OID
    assert len(container.batches) == 1 and len(container.batches[0]) == 3
    event = container.documents[first["eventId"]]
    assert event["changes"][0]["newValue"]["productId"] == "new-product"
    assert event["reason"] == payload["reason"]
    assert backend.create_product(container, payload, context(), GRANTS) == first
    assert len(container.batches) == 1
    with pytest.raises(backend.BackendError) as failure:
        backend.create_product(container, creation_payload(name="Different"), context(), GRANTS)
    assert failure.value.code == "operation_conflict"
    with pytest.raises(backend.BackendError) as failure:
        backend.create_product(container, creation_payload(operationId=TENANT), context(), GRANTS)
    assert failure.value.code == "already_exists"


def test_creation_failure_does_not_leave_partial_product_or_audit():
    container = Container()
    container.fail_create = True
    before = deepcopy(container.documents)
    with pytest.raises(backend.BackendError) as failure:
        backend.create_product(container, creation_payload(), context(), GRANTS)
    assert failure.value.code == "already_exists"
    assert container.documents == before


@pytest.mark.parametrize("change", [
    {"name": ""}, {"description": "x" * 4001}, {"categoryName": None},
    {"productId": backend.SEARCH_QUERY_PARTITION}, {"operationId": "invalid"},
    {"actor": "client-supplied"}, {"commercial": {"priceMinor": 1}},
])
def test_creation_rejects_invalid_or_client_owned_fields(change):
    with pytest.raises(backend.BackendError) as failure:
        backend.create_product(Container(), creation_payload(**change), context(), GRANTS)
    assert failure.value.code == "invalid_request"


def test_creation_authorization_precedes_storage():
    with pytest.raises(backend.BackendError) as failure:
        backend.create_product(None, creation_payload(), context(), {})
    assert failure.value.code == "forbidden"


def test_large_demo_seed_has_1200_unique_products_and_preserves_edits():
    class SeedContainer(Container):
        def execute_item_batch(self, *, batch_operations, partition_key):
            documents = [deepcopy(args[0]) for operation, args, options in batch_operations]
            assert all(item["productId"] == partition_key for item in documents)
            assert all(item["id"] not in self.documents for item in documents)
            self.documents.update({item["id"]: item for item in documents})

    container = SeedContainer()
    grants = {f"{TENANT}:{OID}": ["seed"]}
    for start in range(0, 1200, 50):
        result = backend.seed_demo_catalog(container, start, 50, context(), grants)
        assert len(result["items"]) == 50
    products = [item for item in container.documents.values() if item["docType"] == "product"]
    assert len(products) == len({item["productId"] for item in products}) == 1200
    assert len({item["categoryName"] for item in products}) >= 10
    assert len({item["description"] for item in products}) >= 1000
    assert container.documents["product:bike-100"] == product()
    before = deepcopy(container.documents)
    assert all(item["status"] == "skipped" for item in backend.seed_demo_catalog(
        container, 0, 50, context(), grants,
    )["items"])
    assert container.documents == before


@pytest.mark.parametrize(("start", "count"), [
    (-1, 50), (0, 0), (0, 51), (True, 1), (1199, 2), (1200, 1),
])
def test_large_seed_rejects_invalid_batch_bounds(start, count):
    with pytest.raises(backend.BackendError) as failure:
        backend.seed_demo_catalog(None, start, count, context(), {f"{TENANT}:{OID}": ["seed"]})
    assert failure.value.code == "invalid_request"


class CatalogContainer(Container):
    def query_items(self, **kwargs):
        parameters = {item["name"]: item["value"] for item in kwargs["parameters"]}
        return sorted([
            deepcopy(item) for item in self.documents.values()
            if item["docType"] == "product" and item["productId"] > parameters["@after"]
        ], key=lambda item: item["productId"])[:parameters["@limit"]]


class SearchIndex(Container):
    def __init__(self):
        super().__init__()
        self.documents = {}
        self.ranked = []
        self.headers = []
        self.queries = []

    def upsert_item(self, document):
        self.documents[document["id"]] = deepcopy(document)

    def query_items(self, **kwargs):
        self.queries.append(kwargs)
        for headers in self.headers:
            kwargs["response_hook"](headers, {})
        return deepcopy(self.ranked)


def index_bike(catalog, search):
    return backend.index_product_search(
        catalog, search, {
            "productId": "bike-100", "expectedVersion": catalog.documents["product:bike-100"]["version"],
            "embedding": [0.01] * 1536,
        }, context(), GRANTS,
    )


def test_incremental_status_pagination_includes_missing_then_skips_current():
    catalog, search = CatalogContainer(), SearchIndex()
    assert backend.list_pending_search(catalog, search, 1, "", context(), GRANTS)["items"]
    index_bike(catalog, search)
    state = backend.get_search_index_status(catalog, search, ["bike-100"], context(), GRANTS)
    assert state == {"items": [{
        "productId": "bike-100", "version": 1, "sourceVersion": 1, "status": "current",
    }], "pendingCount": 0}
    page = backend.list_pending_search(catalog, search, 1, "", context(), GRANTS)
    assert page == {"items": [], "afterProductId": "", "scannedCount": 1}
    backend.apply_update(catalog, request(), context(), GRANTS)
    page = backend.list_pending_search(catalog, search, 1, "", context(), GRANTS)
    assert page["items"][0]["version"] == 2
    index_bike(catalog, search)
    assert backend.list_pending_search(catalog, search, 1, "", context(), GRANTS)["items"] == []


def test_pending_scan_advances_cursor_even_when_a_page_is_fully_indexed():
    catalog, search = CatalogContainer(), SearchIndex()
    backend.create_product(catalog, creation_payload(), context(), GRANTS)
    index_bike(catalog, search)
    first = backend.list_pending_search(catalog, search, 1, "", context(), GRANTS)
    assert first["items"] == [] and first["afterProductId"] == "bike-100"
    second = backend.list_pending_search(catalog, search, 1, first["afterProductId"], context(), GRANTS)
    assert second["items"][0]["productId"] == "new-product" and not second["afterProductId"]


@pytest.mark.parametrize("ids", [[], ["bike-100"] * 2, ["unknown"], ["bad id"], ["id"] * 101])
def test_index_status_validates_input_and_missing_products(ids):
    with pytest.raises(backend.BackendError):
        backend.get_search_index_status(Container(), SearchIndex(), ids, context(), GRANTS)


@pytest.mark.parametrize(("version", "status", "requested"), [
    (2, "active", "active"), (1, "deleted", "active"), (1, "deleted", "all"),
])
def test_stale_search_hits_never_escape_authoritative_checks(version, status, requested):
    catalog, search = Container(), SearchIndex()
    search.ranked = [{"productId": "bike-100", "sourceVersion": 1, "status": "active"}]
    catalog.documents["product:bike-100"].update(version=version, status=status)
    result = backend.search_products_by_name(catalog, search, "bike", 10, requested, context(), GRANTS)
    assert result["items"] == [] and result["staleCount"] == 1 and result["indexingPending"]
    assert result["diagnostics"]["requestCharge"] is None


def test_search_diagnostics_aggregate_real_page_headers_without_fabricating_metrics():
    catalog, search = Container(), SearchIndex()
    search.ranked = [{"productId": "bike-100", "sourceVersion": 1, "status": "active"}]
    search.headers = [
        {"x-ms-request-charge": "2.5", "x-ms-documentdb-query-metrics": "page1"},
        {"x-ms-request-charge": "1.25", "x-ms-cosmos-index-utilization": "index"},
    ]
    result = backend.search_products_by_name(catalog, search, "bike", 10, "active", context(), GRANTS)
    assert result["diagnostics"] == {
        "requestCharge": 3.75, "queryMetrics": ["page1"], "indexMetrics": ["index"],
        "scope": "search-query-only",
    }
    assert not result["indexingPending"] and len(result["items"]) == 1


def test_search_comparison_executes_distinct_queries_and_removes_unused_parameters():
    catalog, search = Container(), SearchIndex()
    backend.index_search_query(catalog, search, {
        "queryId": "trail-riding", "label": "Trail riding", "queryText": "outdoor trails",
        "embedding": [0.01] * 1536,
    }, context(), GRANTS)
    result = backend.compare_search_modes(catalog, search, "trail-riding", 5, "active", context(), GRANTS)
    assert set(result) == {"keyword", "vector", "hybrid"}
    keyword, vector, hybrid = search.queries
    assert "FullTextScore" in keyword["query"] and "VectorDistance" not in keyword["query"]
    assert "@queryVector" not in {item["name"] for item in keyword["parameters"]}
    assert "VectorDistance" in vector["query"] and "FullTextScore" not in vector["query"]
    assert "@term0" not in {item["name"] for item in vector["parameters"]}
    assert "RRF(" in hybrid["query"]


@pytest.mark.parametrize("outcome", ["success", "version_conflict", "embedding_error", "storage_error"])
def test_reindex_worker_runs_twice_and_embeds_only_pending_products(monkeypatch, outcome):
    catalog, search = CatalogContainer(), SearchIndex()
    calls = []

    def index_product(payload):
        if outcome == "storage_error":
            raise StorageError(503)
        try:
            return backend.index_product_search(catalog, search, payload, context(), GRANTS)
        except backend.BackendError as error:
            return {"status": "rejected", "code": error.code, "message": str(error)}

    wrapper = SimpleNamespace(
        list_pending_search=lambda pageSize, afterProductId: backend.list_pending_search(
            catalog, search, pageSize, afterProductId, context(), GRANTS,
        ),
        index_product_search=index_product,
    )
    notebookutils = ModuleType("notebookutils")
    setattr(notebookutils, "udf", SimpleNamespace(getFunctions=lambda name: wrapper))
    monkeypatch.setitem(sys.modules, "notebookutils", notebookutils)
    for name in ("synapse", "synapse.ml", "synapse.ml.spark", "synapse.ml.spark.aifunc"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))

    def create_frame(rows, columns):
        calls.append(rows)
        if outcome == "version_conflict":
            catalog.documents["product:bike-100"]["version"] += 1
        embedded = [{
            **dict(zip(columns, row)), "embedding": [0.01] * 1536,
            "embeddingError": "Service error" if outcome == "embedding_error" else None,
        } for row in rows]
        return SimpleNamespace(ai=SimpleNamespace(embed=lambda **kwargs: SimpleNamespace(collect=lambda: embedded)))

    namespace: dict[str, Any] = {"spark": SimpleNamespace(createDataFrame=create_frame)}
    worker = SCENARIO / "02_ProductPimReindex.Notebook/notebook-content.py"
    code = compile(worker.read_text(), str(worker), "exec")
    if outcome == "embedding_error":
        with pytest.raises(RuntimeError, match="Fabric embedding failed"):
            exec(code, namespace)
        assert not search.documents
        return
    if outcome == "storage_error":
        with pytest.raises(StorageError):
            exec(code, namespace)
        assert not search.documents
        return
    exec(code, namespace)
    if outcome == "version_conflict":
        assert namespace["summary"]["indexedCount"] == 0
        assert namespace["summary"]["concurrentProductIds"] == ["bike-100"]
        assert not search.documents
        return
    assert namespace["summary"]["indexedCount"] == 1
    exec(code, namespace)
    assert namespace["summary"]["indexedCount"] == 0
    assert len(calls) == 1
    backend.apply_update(catalog, request(), context(), GRANTS)
    exec(code, namespace)
    assert namespace["summary"]["indexedCount"] == 1
    assert len(calls) == 2
