"""After forcing, the fold serves the memo — never the spent thunk."""

from patternbuffer.buffer import PatternBuffer
from patternbuffer.classify import Classifier
from patternbuffer.indexes import Indexes
from patternbuffer.roles import _make_engine_roles
from patternbuffer.testing import StubModel
from patternbuffer.thunks import INVENT_UNDER_CANON, Resolver


def test_fold_serves_generated_rows_after_force(tmp_path):
    buf = PatternBuffer(tmp_path / "w.world", world_id="w:test")
    stub = StubModel()
    classifier = Classifier(buf, stub)
    indexes = Indexes(buf, classifier)
    roles = _make_engine_roles()
    resolver = Resolver(buf, classifier, indexes, roles["resolver"], stub)

    # Literal aspect: generated row supersedes the spent thunk on the key.
    buf.append(entity="obj:meter", attribute="inscription",
               value={"policy": INVENT_UNDER_CANON}, value_type="unresolved",
               valid_from=1.0, status="assumed", role=roles["ingestor"])
    classifier.classify_all()
    stub.enqueue({"items": [{"value": "TOVAN"}]})
    stub.enqueue({"durability": "CONSTITUTIVE", "class_confidence": 0.9})
    resolver.resolve("obj:meter", "inscription")

    result = indexes.fold_key("obj:meter", "inscription")
    assert not result.conflicted
    assert result.winner.status == "generated"
    assert result.winner.value == "TOVAN"

    # Contents aspect: the key folds to nothing; the tree serves contents.
    buf.append(entity="obj:drawer", attribute="contents",
               value={"policy": INVENT_UNDER_CANON}, value_type="unresolved",
               valid_from=1.0, status="assumed", role=roles["ingestor"])
    classifier.classify_all()
    stub.enqueue({"items": [{"value": "a brass key", "kind": "key"}]})
    resolver.resolve("obj:drawer", "contents")
    assert indexes.fold_key("obj:drawer", "contents").winner is None  # spent thunk hidden
    assert len(indexes.contents("obj:drawer")) == 1
    buf.close()
