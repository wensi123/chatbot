# tests/test_app.py
import unittest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
# 明确地从 transformers 导入被 mock 的类/函数
from transformers import AutoTokenizer, AutoModelForCausalLM # TextIteratorStreamer 已经在 app.py 中导入

# MockStreamer class definition (as before)
class MockStreamer:
    def __init__(self, tokenizer, skip_prompt, skip_special_tokens):
        self.tokenizer = tokenizer
        self.skip_prompt = skip_prompt
        self.skip_special_tokens = skip_special_tokens
    def put(self, value):
        pass
    def end(self):
        pass
    def __iter__(self):
        yield "Hello"
        yield " "
        yield "World"
        yield "!"
    # __next__ can be omitted if __iter__ is sufficient

class ChatbotAppTestCase(unittest.TestCase):

    def setUp(self):
        # 1. Mock for the tokenizer INSTANCE that AutoTokenizer.from_pretrained would return
        self.mock_tokenizer_instance = MagicMock() # Create a general MagicMock first
        # Now, configure the methods for this mock instance
        self.mock_tokenizer_instance.apply_chat_template.return_value = "Formatted prompt" # This should now work
        
        mock_tokenized_output = MagicMock()
        mock_inputs_on_device = MagicMock(input_ids="mock_input_ids", attention_mask="mock_attention_mask")
        mock_tokenized_output.to.return_value = mock_inputs_on_device
        # Configure what tokenizer(...) (i.e., mock_tokenizer_instance.__call__) returns
        self.mock_tokenizer_instance.return_value = mock_tokenized_output # For tokenizer(...)

        # 2. Mock for the model INSTANCE that AutoModelForCausalLM.from_pretrained would return
        self.mock_model_instance = MagicMock() # General MagicMock
        # model.generate will be configured/asserted in tests

        # 3. Mock for TextIteratorStreamer instantiation
        self.mock_streamer_instance = MockStreamer(self.mock_tokenizer_instance, True, True) 
        self.mock_text_iterator_streamer_class = MagicMock(return_value=self.mock_streamer_instance)

        # Start patches
        # Patch AutoTokenizer.from_pretrained to return our pre-configured mock_tokenizer_instance
        self.patch_tokenizer_from_pretrained = patch('transformers.AutoTokenizer.from_pretrained', return_value=self.mock_tokenizer_instance)
        # Patch AutoModelForCausalLM.from_pretrained to return our pre-configured mock_model_instance
        self.patch_model_from_pretrained = patch('transformers.AutoModelForCausalLM.from_pretrained', return_value=self.mock_model_instance)
        
        # Patch TextIteratorStreamer class in app.py
        self.patch_text_iterator_streamer = patch('app.TextIteratorStreamer', self.mock_text_iterator_streamer_class)

        self.mock_auto_tokenizer_from_pretrained_method = self.patch_tokenizer_from_pretrained.start()
        self.mock_auto_model_from_pretrained_method = self.patch_model_from_pretrained.start()
        self.mock_tis_cls_in_app = self.patch_text_iterator_streamer.start()

        self.addCleanup(self.patch_tokenizer_from_pretrained.stop)
        self.addCleanup(self.patch_model_from_pretrained.stop)
        self.addCleanup(self.patch_text_iterator_streamer.stop)

        # Create the app AFTER patches are in place
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        # Verify that from_pretrained methods were called (i.e., load_model was run with patches active)
        self.mock_auto_tokenizer_from_pretrained_method.assert_called_once()
        self.mock_auto_model_from_pretrained_method.assert_called_once()

    def tearDown(self):
        pass # Patches are stopped by addCleanup

    def test_index_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('聊天机器人', response.data.decode('utf-8'))

    def test_chat_stream(self):
        response = self.client.post('/chat', json={'message': '你好', 'history': []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/event-stream')

        stream_data = b""
        for chunk in response.response: 
            stream_data += chunk
        decoded_data = stream_data.decode('utf-8')
        
        # Verify TextIteratorStreamer class was instantiated
        self.mock_tis_cls_in_app.assert_called_once_with(self.mock_tokenizer_instance, skip_prompt=True, skip_special_tokens=True)
        
        # Verify tokenizer instance methods were called
        self.mock_tokenizer_instance.apply_chat_template.assert_called_once()
        args_template, kwargs_template = self.mock_tokenizer_instance.apply_chat_template.call_args
        self.assertEqual(args_template[0], [{"role": "user", "content": "你好"}])
        self.assertTrue(kwargs_template.get('add_generation_prompt'))

        # Verify tokenizer instance was called (as a function)
        self.mock_tokenizer_instance.assert_called_with(['Formatted prompt'], return_tensors="pt")
        # Verify .to(device) was called on the result of tokenizer(...)
        # self.mock_tokenizer_instance.return_value is the mock for tokenizer(...) output
        self.mock_tokenizer_instance.return_value.to.assert_called_once_with('cpu')
        
        # Verify model.generate was called on the model instance
        self.mock_model_instance.generate.assert_called_once() 
        # More specific checks for generate arguments if needed:
        # _, generate_kwargs = self.mock_model_instance.generate.call_args
        # self.assertEqual(generate_kwargs['input_ids'], "mock_input_ids")
        # self.assertEqual(generate_kwargs['streamer'], self.mock_streamer_instance)

        expected_sse_data = "data: Hello\n\ndata:  \n\ndata: World\n\ndata: !\n\n"
        self.assertEqual(decoded_data, expected_sse_data)

    def test_chat_no_message(self):
        # This test doesn't involve the model/tokenizer mocks directly from setUp in its main flow,
        # but the app setup (create_app) still runs.
        response = self.client.post('/chat', json={})
        self.assertEqual(response.status_code, 400)
        json_data = response.get_json()
        self.assertEqual(json_data['error'], 'No message provided')

    def test_chat_with_history(self):
        history = [{"role": "user", "content": "之前的问题"}, {"role": "assistant", "content": "之前的回答"}]
        response = self.client.post('/chat', json={'message': '新问题', 'history': history})
        self.assertEqual(response.status_code, 200)
        
        self.mock_tokenizer_instance.apply_chat_template.assert_called_once()
        args, kwargs = self.mock_tokenizer_instance.apply_chat_template.call_args
        expected_messages = [
            {"role": "user", "content": "之前的问题"},
            {"role": "assistant", "content": "之前的回答"},
            {"role": "user", "content": "新问题"}
        ]
        self.assertEqual(args[0], expected_messages)
        self.mock_model_instance.generate.assert_called_once()

if __name__ == '__main__':
    unittest.main()