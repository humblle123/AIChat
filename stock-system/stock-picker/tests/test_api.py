"""API 集成测试: 用 TestClient 跑 5 个端点 + 公式校验。"""
import pytest
from fastapi.testclient import TestClient

import data.store as store
from app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:
    def test_health(self, client):
        r = client.get('/api/health')
        assert r.status_code == 200
        assert r.json()['status'] == 'ok'

    def test_health_live(self, client):
        r = client.get('/api/health/live')
        assert r.status_code == 200
        assert r.json()['status'] == 'alive'

    def test_health_ready(self, client):
        r = client.get('/api/health/ready')
        assert r.status_code == 200
        body = r.json()
        # 空 DB 应该 not_ready
        assert body['status'] == 'not_ready'
        assert 'stock_basic_count' in body
        assert 'template_cached_count' in body
        assert 'latest_trade_date' in body

    def test_root(self, client):
        r = client.get('/')
        assert r.status_code == 200
        assert r.json()['name'] == 'Smart Stock Picker'


class TestFormulaTemplates:
    def test_list_templates(self, client):
        r = client.get('/api/formula/templates')
        assert r.status_code == 200
        templates = r.json()
        assert len(templates) == 4
        ids = {t['strategy_id'] for t in templates}
        assert ids == {'b1', 's2', 's3', 'kd1'}
        for t in templates:
            assert t['expression']
            assert t['group_name']
            assert t['enabled']


class TestFormulaValidate:
    @pytest.mark.parametrize('expr,expected_valid', [
        ('RPS50 > 90', True),
        ('KDJ_J < 18 AND CLOSE > ZXDQ', True),
        ('MA(CLOSE, 5) > MA(CLOSE, 20)', True),
        ('CLOSE >', False),
        ('', False),
    ])
    def test_validate(self, client, expr, expected_valid):
        r = client.post('/api/formula/validate', json={'formula': expr})
        assert r.status_code == 200
        body = r.json()
        assert body['valid'] is expected_valid


class TestSearch:
    def test_empty_search(self, client):
        r = client.post('/api/stocks/search', json={})
        assert r.status_code == 200
        body = r.json()
        assert body['total'] == 0
        assert body['items'] == []

    def test_search_with_filters(self, client):
        store.save_stock_basic([
            {'code': '600519', 'name': '贵州茅台', 'market': 'SHA', 'is_st': 0, 'listed_date': '2001-08-27'},
        ])
        r = client.post('/api/stocks/search', json={'keyword': '茅台', 'page_size': 10})
        assert r.status_code == 200
        body = r.json()
        assert body['total'] == 1
        assert body['items'][0]['code'] == '600519'


class TestTemplateResults:
    def test_missing_template_id(self, client):
        r = client.post('/api/stocks/template-results', json={'page': 1, 'page_size': 10})
        # 端点要求 template_id,缺则 400
        assert r.status_code in (400, 422)

    def test_nonexistent_template(self, client):
        r = client.post('/api/stocks/template-results', json={'template_id': 99999, 'page': 1, 'page_size': 10})
        assert r.status_code == 400


class TestStockDetail:
    def test_404(self, client):
        r = client.get('/api/stocks/000000')
        assert r.status_code == 404


class TestKLine:
    @pytest.mark.parametrize('period', ['day', 'week', 'month'])
    def test_404(self, client, period):
        r = client.get(f'/api/kline/000000?period={period}')
        assert r.status_code == 404


class TestOpenAPI:
    def test_docs_available(self, client):
        r = client.get('/openapi.json')
        assert r.status_code == 200
        body = r.json()
        assert body['info']['title'] == 'Smart Stock Picker'
        assert 'tags' in body
