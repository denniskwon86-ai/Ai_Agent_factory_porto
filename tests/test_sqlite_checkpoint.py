"""SqliteSaver 영속성(재시작 내성) 회귀 테스트.

핵심 불변식: 체크포인트가 디스크에 보존되어, 새 saver 인스턴스(=서버 재시작)에서 복구된다.
pytest-asyncio 없이 asyncio.run 으로 구동한다.
"""
import asyncio
from langgraph.checkpoint.base import empty_checkpoint


def test_async_sqlite_persists_across_instances(tmp_path):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    import aiosqlite
    db = str(tmp_path / "ckpt.db")
    cfg = {"configurable": {"thread_id": "t1", "checkpoint_ns": ""}}

    async def write():
        conn = await aiosqlite.connect(db, check_same_thread=False)
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        await saver.aput(cfg, empty_checkpoint(),
                         {"source": "test", "step": 0, "writes": {}, "parents": {}}, {})
        await conn.close()

    async def restart_and_read():
        conn = await aiosqlite.connect(db, check_same_thread=False)
        saver = AsyncSqliteSaver(conn)
        got = await saver.aget_tuple(cfg)
        await conn.close()
        return got is not None

    asyncio.run(write())
    # 새 인스턴스(서버 재시작 모사)에서 체크포인트가 복구되어야 한다 (MemorySaver 였다면 실패)
    assert asyncio.run(restart_and_read()) is True


def test_runtime_app_uses_persistent_checkpointer(tmp_path, monkeypatch):
    # get_runtime_app 가 휘발성 MemorySaver 가 아닌 AsyncSqliteSaver 로 컴파일하는지 회귀 가드
    import core.agent_graph as ag
    import config as cfg
    monkeypatch.setattr(cfg, "PIPELINE_DB_FILE", str(tmp_path / "runtime.db"))
    ag._runtime_saver = None      # 캐시 초기화(테스트 격리)
    ag._runtime_apps = {}
    try:
        app = asyncio.run(ag.get_runtime_app("default"))
        assert type(app).__name__ == "CompiledStateGraph"
        assert type(app.checkpointer).__name__ == "AsyncSqliteSaver"
    finally:
        ag._runtime_saver = None
        ag._runtime_apps = {}


def test_runtime_app_caches_per_template(tmp_path, monkeypatch):
    # T2-b: 같은 template_id 는 동일 인스턴스(캐시), 체크포인터(saver)는 템플릿 간 공유
    import core.agent_graph as ag
    import config as cfg
    monkeypatch.setattr(cfg, "PIPELINE_DB_FILE", str(tmp_path / "rt.db"))
    ag._runtime_saver = None
    ag._runtime_apps = {}
    try:
        async def go():
            a1 = await ag.get_runtime_app("default")
            a2 = await ag.get_runtime_app("default")
            return a1, a2
        a1, a2 = asyncio.run(go())
        assert a1 is a2  # 동일 템플릿 → 캐시된 동일 그래프
        assert a1.checkpointer is ag._runtime_saver  # saver 공유
    finally:
        ag._runtime_saver = None
        ag._runtime_apps = {}


def test_studio_app_still_compiles():
    # 스튜디오/테스트용 동기 app(create_factory_graph)은 여전히 동작해야(MemorySaver)
    import core.agent_graph as ag
    assert type(ag.app).__name__ == "CompiledStateGraph"
    assert type(ag.create_factory_graph()).__name__ == "CompiledStateGraph"
