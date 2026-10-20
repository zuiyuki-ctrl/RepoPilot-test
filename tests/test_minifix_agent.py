"""Offline simulated model tests; no provider, SQL or Docker calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch
import agent
from registrations import registration


def response(content='def f(): return 1\n', path='task_list.py'):
    return dict(status='succeeded', finish_reason='stop', truncated=False,
        message=dict(role='assistant', content=json.dumps(dict(file_path=path, content=content))))


class MiniFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'task_list.py'
        self.original = '\n'.join(f'# line {i}' for i in range(20)) + '\ndef f(): return 0\n'
        self.target.write_text(self.original, encoding='utf-8')
        self.data = dict(protocol_version=1, case_id='task-list', case_version='v1',
                         task_description='Fix f', editable_files=['task_list.py'])

    def test_context_difference(self):
        a, b = [agent.make_messages('Fix f', 'task_list.py', self.original, s) for s in ('prefix', 'full')]
        self.assertEqual(a[0], b[0])
        left, right = [json.loads(x[1]['content']) for x in (a, b)]
        self.assertEqual(left['source'], ''.join(self.original.splitlines(True)[:12]))
        self.assertEqual(right['source'], self.original)
        self.assertFalse(left['context_complete'])
        self.assertTrue(right['context_complete'])
        self.assertEqual(left['task'], right['task'])

    def test_writes_model_content_without_claiming_correctness(self):
        model = Mock(return_value=response('def unrelated(): return 42\n'))
        agent.execute(self.data, self.root, 'full', model)
        self.assertEqual(self.target.read_text(), 'def unrelated(): return 42\n')
        model.assert_called_once()
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_bad_outputs_never_write(self):
        candidates = [response('broken syntax('), response(path='tests/test_task_list.py'),
            response(''), response('x'*16001), dict(response(), finish_reason='length'),
            dict(response(), truncated=True), dict(response(), status='failed'),
            dict(response(), message={}),
            dict(response(), message={'role':'assistant', 'content':'```json\n{}\n```'})]
        for candidate in candidates:
            with self.subTest(candidate=str(candidate)[:60]):
                with self.assertRaises(agent.AgentError):
                    agent.execute(self.data, self.root, 'full', Mock(return_value=candidate))
                self.assertEqual(self.target.read_text(), self.original)

    def test_scope_refused_before_call(self):
        for path in ('../outside.py', '/abs.py', 'C:/evil.py', 'tests/t.py', 'test_x.py', 'a\\b.py'):
            model = Mock()
            with self.subTest(path=path), self.assertRaises(agent.AgentError):
                agent.execute(dict(self.data, editable_files=[path]), self.root, 'full', model)
            model.assert_not_called()

    def test_probe_offline_no_edit(self):
        model = Mock()
        agent.execute(dict(self.data, case_version='protocol-probe-v1', repository_commit='0'*40),
                      self.root, 'prefix', model)
        model.assert_not_called()
        self.assertEqual(self.target.read_text(), self.original)

    def test_stale_source(self):
        def model(messages):
            self.target.write_text('# changed\n')
            return response()
        with self.assertRaisesRegex(agent.AgentError, 'source_changed'):
            agent.execute(self.data, self.root, 'full', model)
        self.assertEqual(self.target.read_text(), '# changed\n')

    def test_no_gateway_fallback(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaisesRegex(agent.AgentError, 'gateway_not_configured'):
            agent.call_gateway([])

    def test_gateway_request_no_retry(self):
        transport = MagicMock()
        transport.open.return_value.__enter__.return_value.status = 200
        transport.open.return_value.__enter__.return_value.read.return_value = json.dumps(response()).encode()
        env = dict(REPOPILOT_MODEL_GATEWAY_URL='http://model-gateway:8080/v1/model-calls',
                   REPOPILOT_MODEL_CREDENTIAL_FILE='/run/repopilot/credential')
        with patch.dict('os.environ', env, clear=True), patch.object(Path, 'read_text', return_value='fake-token'), \
                patch.object(agent.http, 'build_opener', return_value=transport):
            self.assertEqual(agent.call_gateway([{'role':'user', 'content':'fix'}])['status'], 'succeeded')
            req = transport.open.call_args.args[0]
            self.assertEqual(set(json.loads(req.data)), {'call_id', 'messages'})
            self.assertEqual(req.get_header('Authorization'), 'Bearer fake-token')
            transport.open.assert_called_once()
            transport.open.reset_mock()
            transport.open.side_effect = TimeoutError()
            with self.assertRaisesRegex(agent.AgentError, 'gateway_unavailable'):
                agent.call_gateway([])
            transport.open.assert_called_once()

    def test_catalog_contract_one_strategy_difference(self):

        a, b = [registration('sha256:'+'a'*64, s) for s in ('prefix', 'full')]

        self.assertNotEqual(a['process']['argv'], b['process']['argv'])
        for x in (a, b):
            x.pop('version'); x['process'].pop('argv')
        self.assertEqual(a, b)


if __name__ == '__main__':
    unittest.main()
