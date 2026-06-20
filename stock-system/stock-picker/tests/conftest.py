"""测试 fixtures 共享。

每个测试用临时 sqlite DB + 清空 store._CONN,确保隔离。
"""
import os
import tempfile
import pytest


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch):
    """每个测试用一个临时 sqlite 文件,且强制重置单例连接。"""
    import config as config_mod
    import data.store as store

    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    # 改两个地方的 DB_PATH: config 源 + data.store 模块属性
    monkeypatch.setattr(config_mod, 'DB_PATH', tmp.name)
    monkeypatch.setattr(config_mod, 'DATA_DIR', os.path.dirname(tmp.name))
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
