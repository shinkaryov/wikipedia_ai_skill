"""One offline dialogue: clarification, terminal reply, real replay, clean exit."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import evaluate_openrouter as runner
from core import load


class InteractiveRunnerTests(unittest.TestCase):
    def test_clarification_continues_same_session_and_creates_report(self):
        prompt = 'Compare astronomy interest in Ukraine and Czechia.'
        reply = 'Use Ukrainian and Czech Wikipedia and the saved study dates.'
        question = 'Compare Ukrainian and Czech language editions, rather than countries?'
        requests = []
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'session'

            def response(request, timeout):
                messages = json.loads(request.data)['messages']
                requests.append(messages)
                if len(requests) == 1:
                    shutil.copytree(runner.ROOT / 'examples/astronomy-uk-cs', output / 'evidence')
                    message = {'role': 'assistant', 'content': question}
                elif len(requests) == 2:
                    self.assertEqual(messages[-1]['content'], reply)
                    self.assertIn(question, [m.get('content') for m in messages])
                    argv = ['replay', '--run', 'evidence', '--out', 'study']
                    message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                        'id': 'replay-call', 'type': 'function', 'function': {
                            'name': 'wiki_cli', 'arguments': json.dumps({'argv': argv})}}]}
                else:
                    result = json.loads(messages[-1]['content'])
                    self.assertEqual(result['returncode'], 0, result)
                    message = {'role': 'assistant', 'content': 'Report created in study/brief.pdf.'}
                return io.BytesIO(json.dumps({'model': 'test-stub', 'choices': [{'message': message}]}).encode())

            stdout, stderr = io.StringIO(), io.StringIO()
            argv = ['runner', '--model', 'test-stub', '--interactive', '--prompt', prompt,
                    '--max-turns', '2', '--out', str(output)]
            with patch.object(sys, 'argv', argv), patch.object(sys, 'stdin', io.StringIO('\n' + reply + '\n/exit\n')), \
                 patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-placeholder'}), \
                 patch.object(runner.urllib.request, 'urlopen', side_effect=response), \
                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(runner.main(), 0)
            self.assertEqual(len(requests), 3)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(len(result['answers']), 2)
            self.assertIn(question, stderr.getvalue())
            self.assertIn('You (/exit to finish):', stderr.getvalue())
            trace = load(output / 'trace.json')
            self.assertTrue(trace['interactive'])
            self.assertEqual(trace['prompts'], [prompt, reply])
            self.assertEqual([m['content'] for m in requests[-1] if m['role'] == 'user'], [prompt, reply])
            self.assertEqual(len(PdfReader(output / 'study/brief.pdf').pages), 1)
            self.assertEqual(load(output / 'study/metrics.json')['metrics'],
                             load(output / 'evidence/metrics.json')['metrics'])
            self.assertGreater((output / 'study/trend.png').stat().st_size, 0)


if __name__ == '__main__':
    unittest.main()
