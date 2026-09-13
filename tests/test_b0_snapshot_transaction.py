"""호출자 연결을 넘긴 get/list가 재잠금·조기 commit을 하지 않는지 확인한다."""
import pytest

from core.data_preparation.store import DataPreparationStore
from tests.test_data_usage_holds import prepare


@pytest.mark.parametrize("read", ["get", "list"])
def test_projection_uses_caller_connection_and_keeps_rollback(tmp_path, read):
    store = DataPreparationStore(str(tmp_path / "caller.db"))
    binding, snap = prepare(store, tmp_path, key="FND-03")
    original = store.get_snapshot(snap["snapshot_id"])
    statements = []
    with pytest.raises(RuntimeError, match="TEST_ROLLBACK"):
        with store.transaction() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE dataset_snapshots SET row_count=42 WHERE snapshot_id=?", (snap["snapshot_id"],))
            conn.set_trace_callback(statements.append)
            row = (store.get_snapshot(snap["snapshot_id"], conn=conn) if read == "get"
                   else store.list_snapshots(binding["instance_id"], conn=conn)[0])
            assert row["row_count"] == 42 and row["usage_holds"] == []
            assert conn.in_transaction
            assert not any(sql.startswith(("BEGIN", "COMMIT", "ROLLBACK")) for sql in statements)
            raise RuntimeError("TEST_ROLLBACK")
    assert store.get_snapshot(snap["snapshot_id"]) == original
