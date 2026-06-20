"""测试 fixtures 共享。

约定: 每个测试用临时 sqlite DB + 清空 store._CONN,确保隔离。
"""
import os
import tempfile
import pytest


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch):
    """每个测试用一个临时 sqlite 文件,且强制重置单例连接。"""
    import data.store as store

    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    monkeypatch.setattr(store, 'DB_PATH', tmp.name)
    monkeypatch.setattr(store, 'DATA_DIR', os.path.dirname(tmp.name))
    store._CONN = None
    store.init_db()
    yield
    store._CONN = None
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
