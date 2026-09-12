"""Contract tests exercise the installed Supabase SDK against an HTTP stub, not a live database."""
import json
from unittest.mock import Mock
import httpx
import pytest
from app.repositories.supabase_repository import SupabaseRepository
from app.errors import Conflict

@pytest.fixture
def remote():
    from supabase import create_client
    from supabase.lib.client_options import SyncClientOptions
    calls = []
    def handle(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, str(request.url.query), body))
        if 'commit_assessment_answer' in request.url.path:
            return httpx.Response(204)
        if 'create_catalog_assessment' in request.url.path:
            return httpx.Response(200, json=body['p_assessment'])
        if 'create_candidate_attempt' in request.url.path:
            return httpx.Response(200, json=body['p_attempt'])
        return httpx.Response(200, json=[body] if body else [], headers={'Content-Range': '0-0/1'})
    client = httpx.Client(transport=httpx.MockTransport(handle))
    repo = SupabaseRepository.__new__(SupabaseRepository)
    repo.client = create_client('https://test.supabase.co', 'test-server-key', options=SyncClientOptions(httpx_client=client))
    return repo, calls

def test_assessment_rpc(remote):
    repo,calls = remote
    assert repo.create_assessment({'id':'123','title':'QA'})['title'] == 'QA'
    assert calls[-1][1].endswith('/rpc/create_catalog_assessment')

def test_upsert_unique_response(remote):
    repo,calls = remote
    data = {'id':'r','attempt_id':'a','question_id':'q'}
    assert repo.save_response(data) == data
    assert 'on_conflict=attempt_id%2Cquestion_id' in calls[-1][2]

def test_atomic_commit_rpc(remote):
    repo,calls = remote
    repo.commit_answer(2,{'id':'a','version':3},{'id':'r'},None)
    assert calls[-1][1].endswith('/rpc/commit_assessment_answer')
    assert calls[-1][3] == {'p_version':2,'p_attempt':{'id':'a','version':3},'p_response':{'id':'r'},'p_report':None}

def test_queries_and_no_row(remote):
    repo,calls = remote
    assert repo.get_attempt('a') is None
    assert repo.list_questions('a') == []
    assert 'assessment_id=eq.a' in calls[-1][2]

def test_conflict_mapping(remote):
    repo,_ = remote
    repo.client.rpc = Mock(side_effect=RuntimeError('attempt_conflict'))
    with pytest.raises(Conflict): repo.commit_answer(0,{}, {},None)

def test_pagination():
    repo = SupabaseRepository.__new__(SupabaseRepository)
    query = Mock(); query.select.return_value = query; query.order.return_value = query; query.range.return_value = query
    query.execute.side_effect = [Mock(data=[{'id':str(i)} for i in range(500)]), Mock(data=[{'id':'last'}])]
    repo.client = Mock(); repo.client.table.return_value = query
    assert len(repo.list_attempts()) == 501
    assert query.range.call_args_list[1].args == (500,999)

def test_candidate_attempt_rpc(remote):
    repo,calls = remote
    assert repo.create_attempt({'id':'a','candidate_name':'QA'})['id'] == 'a'
    assert calls[-1][1].endswith('/rpc/create_candidate_attempt')
