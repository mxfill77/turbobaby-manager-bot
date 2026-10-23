"""No network. Copy to VPS tests/ before the complete restart gate."""
import ast
from datetime import datetime, timezone
import importlib.util
import logging
import os
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(os.environ.get('CRM_FEED_SOURCE_ROOT', str(Path(__file__).resolve().parents[1])))


def function(name, source, namespace):
    tree = ast.parse((ROOT / source).read_text(encoding='utf-8'))
    node = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), source, 'exec'), namespace)
    return namespace[name]


def immediate(coroutine):
    # This capture handler must finish without any await/network operation.
    try:
        coroutine.send(None)
    except StopIteration:
        return
    raise AssertionError('edit observer unexpectedly suspended')


class FeedMediaTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('crm_test_topic_feed', ROOT / 'topic_feed.py')
        self.feed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.feed)
        self.chat = -1002751134848
        self.message = SimpleNamespace(chat_id=self.chat, message_thread_id=1051, message_id=12980,
            date=datetime(2026, 10, 19, 10, tzinfo=timezone.utc), edit_date=None,
            text=None, caption='Работа сделана', media_group_id='album001', reply_to_message=None,
            from_user=SimpleNamespace(is_bot=False),
            photo=[SimpleNamespace(file_id='smaller_file_id', file_unique_id='smaller_unique', width=90, height=90, file_size=123),
                   SimpleNamespace(file_id='AgACAgIAAxkBAA_example', file_unique_id='AQADabcdef012345', width=1280, height=960, file_size=12345)])

    def test_largest_photo_metadata_is_preserved_without_download(self):
        self.assertEqual(self.feed.message_media(self.message), [{'file_id': 'AgACAgIAAxkBAA_example',
            'file_unique_id': 'AQADabcdef012345', 'width': 1280, 'height': 960, 'file_size': 12345}])
        self.assertEqual(self.feed.message_media(SimpleNamespace(photo=[])), [])

    def test_existing_incoming_feed_receives_photo_references_and_edit_time(self):
        calls = []
        self.feed.append = lambda *args, **kwargs: calls.append((args, kwargs)) or True
        namespace = {'_feed_servicing': lambda chat: chat == self.chat, '_tfeed': self.feed,
                     '_feed_role': lambda author: 'staff', 'log': logging.getLogger('test')}
        incoming = function('feed_incoming', 'splinter.py', namespace)
        self.message.edit_date = datetime(2026, 10, 19, 10, 10, tzinfo=timezone.utc)
        self.assertTrue(incoming(self.message))
        self.assertEqual(calls[0][0], (self.chat, 1051, 'photo'))
        self.assertEqual(calls[0][1]['media'][0]['file_id'], 'AgACAgIAAxkBAA_example')
        self.assertEqual(calls[0][1]['edited_at'], self.message.edit_date.timestamp())
        self.assertEqual(calls[0][1]['text'], 'Работа сделана')

    def test_edit_handler_observes_only_without_business_calls(self):
        calls = []
        fake = SimpleNamespace(GROUPS={self.chat: 'servicing'}, feed_incoming=lambda msg: calls.append(msg))
        namespace = {'splinter': fake, 'Update': object, 'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object)}
        handle = function('capture_service_edit', 'bot.py', namespace)
        immediate(handle(SimpleNamespace(edited_message=self.message), None))
        self.assertEqual(calls, [self.message])
        immediate(handle(SimpleNamespace(edited_message=None), None))
        self.message.chat_id = -123
        immediate(handle(SimpleNamespace(edited_message=self.message), None))
        self.assertEqual(len(calls), 1)

    def test_new_topic_reads_canonical_db_on_cache_miss_without_restart(self):
        calls = []
        memory = SimpleNamespace(get_topic_bike=lambda chat, topic: calls.append((chat, topic)) or 'NEW BIKE EXACT NAME')
        namespace = {'SERVICING_CHAT': self.chat, '_TOPIC_BIKE_OVERRIDE': {}, '_TOPIC_NAMES': {},
                     '_MEMORY': memory, '_load_topic_map': lambda: {}, 'log': logging.getLogger('test')}
        resolve = function('bike_from_topic', 'splinter.py', namespace)
        self.assertEqual(resolve(self.chat, 15000), 'NEW BIKE EXACT NAME')
        self.assertEqual(resolve(self.chat, 15000), 'NEW BIKE EXACT NAME')
        self.assertEqual(calls, [(self.chat, 15000)])

    def test_manual_override_still_wins_without_db_read(self):
        namespace = {'SERVICING_CHAT': self.chat, '_TOPIC_BIKE_OVERRIDE': {(self.chat, 1051): 'MANUAL BIKE'},
                     '_TOPIC_NAMES': {}, '_MEMORY': object(), '_load_topic_map': lambda: {}, 'log': logging.getLogger('test')}
        resolve = function('bike_from_topic', 'splinter.py', namespace)
        self.assertEqual(resolve(self.chat, 1051), 'MANUAL BIKE')


if __name__ == '__main__':
    unittest.main()
