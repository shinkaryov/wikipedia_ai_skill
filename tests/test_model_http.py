"""Bounded OpenRouter retries; no live requests or waits."""
import io
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import evaluate_openrouter as runner
from core import ResearchError


def failure(status, retry_after=None):
    body = {'error': {'message': 'Provider rejected secret-key',
                      'metadata': {'provider_name': 'Example', 'raw': 'not for logging'}}}
    return HTTPError('https://example.invalid', status, 'error',
                     {'Retry-After': retry_after} if retry_after else {},
                     io.BytesIO(json.dumps(body).encode()))


class ModelHTTPTests(unittest.TestCase):
    def test_recovers_after_rate_limit_then_server_error(self):
        success = io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')
        with patch.object(runner.urllib.request, 'urlopen', side_effect=[failure(429, '3'), failure(503), success]) as request, \
             patch.object(runner.time, 'sleep') as sleep:
            result = runner.completion('test', [], 'secret-key')
        self.assertEqual(result['choices'][0]['message']['content'], 'ok')
        self.assertEqual(request.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [3, 4])

    def test_retry_budget_and_safe_error_details(self):
        with patch.object(runner.urllib.request, 'urlopen', side_effect=[failure(429) for _ in range(3)]) as request, \
             patch.object(runner.time, 'sleep') as sleep:
            with self.assertRaises(ResearchError) as raised:
                runner.completion('test', [], 'secret-key')
        details = raised.exception.as_dict()
        self.assertEqual((request.call_count, sleep.call_count), (3, 2))
        self.assertEqual(details['attempts'], 3)
        self.assertEqual(details['provider'], 'Example')
        self.assertNotIn('secret-key', json.dumps(details))
        self.assertNotIn('not for logging', json.dumps(details))

    def test_no_retry_for_permanent_error_or_long_retry_after(self):
        date = format_datetime(datetime.now(timezone.utc) + timedelta(minutes=5), usegmt=True)
        for status, header in [(404, None), (429, '120'), (503, date)]:
            with self.subTest(status=status, header=header), \
                 patch.object(runner.urllib.request, 'urlopen', side_effect=failure(status, header)) as request, \
                 patch.object(runner.time, 'sleep') as sleep:
                with self.assertRaises(ResearchError) as raised:
                    runner.completion('test', [], 'secret-key')
                self.assertEqual(request.call_count, 1)
                sleep.assert_not_called()
                self.assertEqual(raised.exception.as_dict()['status'], status)
                if header:
                    self.assertGreater(raised.exception.as_dict()['retry_after_seconds'], 60)


if __name__ == '__main__':
    unittest.main()
