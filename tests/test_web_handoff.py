from memory_hub.web import render_handoff


def test_structured_handoff_is_visible_and_escaped():
    html = render_handoff({
        'to_worker': 'ai-b',
        'summary': 'Review <script>bad()</script>',
        'result_commit': 'deadbeef123',
        'changed_artifacts': ['src/feature.py'],
        'blockers': ['PostgreSQL test pending'],
        'next_steps': ['Run integration checks'],
        'test_results': [
            {'command': 'pytest -q', 'status': 'passed', 'details': 'Unit checks passed'},
            {'command': 'docker compose build', 'status': 'not_run', 'details': 'Docker absent'},
            {'command': 'adversarial test', 'status': 'failed', 'details': '<img src=x onerror=bad()>'},
        ],
    })
    for expected in ['ai-b', 'deadbeef123', 'src/feature.py', 'PostgreSQL test pending',
                     'Run integration checks', 'pytest -q', '通過', '未執行', '失敗',
                     'Docker absent', '接手者仍需自行驗證']:
        assert expected in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '<img' not in html and '&lt;img' in html


def test_legacy_handoff_missing_fields_stays_readable():
    html = render_handoff({'summary': 'Older record', 'to_worker': 'ai-c'})
    assert 'Older record' in html and '未提供' in html and '未列項目' in html


def test_recovery_history_visible_and_escaped():
    from memory_hub.web import render_recovery
    html = render_recovery({'recovered_by':'operator','at':1000,'fence':8,
                            'reason':'Worker unavailable <script>x</script>','to_worker':'ai-d'})
    assert 'operator' in html and 'ai-d' in html and 'Fence 8' in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '先前租約與脈絡包已失效' in html


def test_unassigned_recovery_is_explicit():
    from memory_hub.web import render_recovery
    assert '解除指定，可重新認領' in render_recovery({'reason':'Retired identity','to_worker':None})
