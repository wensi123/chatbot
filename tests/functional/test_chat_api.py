import unittest
import requests # 用于发送HTTP请求
import time # 用于在流式请求之间稍作等待
import json
import os

# 假设你的Flask应用运行在 http://127.0.0.1:5001
BASE_URL = "http://127.0.0.1:5001"

# 注意: 运行此测试前，请确保 Flask 应用 (app.py) 正在运行！
# 并且模型已经加载完成。

class ChatAppFunctionalTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 可以在这里添加一个简单的检查，看服务器是否在运行
        # 但更可靠的是在运行测试脚本前手动启动服务器
        print("确保 Flask 应用正在运行在 {} ...".format(BASE_URL))
        try:
            requests.get(BASE_URL, timeout=2) # 尝试连接
        except requests.exceptions.ConnectionError:
            print(f"无法连接到服务器 {BASE_URL}. 请先启动 Flask 应用。")
            # 可以选择在这里 sys.exit(1) 或者让测试因超时而失败
            raise ConnectionError(f"无法连接到服务器 {BASE_URL}. 请先启动 Flask 应用。")
        print("服务器连接成功，开始功能测试...")


    def test_01_index_page_loads(self):
        """测试首页是否成功加载"""
        response = requests.get(BASE_URL + "/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<!DOCTYPE html>", response.text)
        self.assertIn("<title>智能聊天助手</title>", response.text) # 根据你的HTML title

    def test_02_chat_single_message_stream(self):
        """测试单轮聊天流式响应"""
        url = BASE_URL + "/chat"
        payload = {
            "message": "你好，机器人！",
            "history": []
        }
        headers = {'Content-Type': 'application/json'}

        # 使用 stream=True 来处理流式响应
        with requests.post(url, json=payload, headers=headers, stream=True, timeout=30) as response: # 增加超时
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['Content-Type'], 'text/event-stream; charset=utf-8') # Flask 可能会添加 charset

            received_data = ""
            chunk_count = 0
            for chunk in response.iter_content(chunk_size=None): # chunk_size=None 保持服务器发送的大小
                if chunk:
                    decoded_chunk = chunk.decode('utf-8')
                    print(f"收到块: {decoded_chunk.strip()}") # 打印方便调试
                    self.assertTrue(decoded_chunk.startswith("data:") or decoded_chunk == "\n" or decoded_chunk.startswith("event:")) # SSE格式
                    if decoded_chunk.startswith("data:"):
                        content = decoded_chunk[len("data:"):].strip()
                        if content and content != "[END_OF_STREAM]" and not content.startswith("[ERROR]"): # 假设的结束标记
                            received_data += content
                            chunk_count += 1
            
            print(f"完整回复: {received_data}")
            self.assertGreater(chunk_count, 0, "应至少收到一个数据块")
            self.assertTrue(len(received_data) > 0, "收到的回复不应为空")
            # 对于AI生成的内容，很难精确断言，但可以检查一些通用模式
            # 例如，可以检查它是否包含非空字符
            self.assertTrue(any(c.isalnum() for c in received_data), "回复应包含有效字符")

    def test_03_chat_with_history_stream(self):
        """测试带历史记录的多轮聊天流式响应"""
        url = BASE_URL + "/chat"
        headers = {'Content-Type': 'application/json'}

        # 第一轮
        payload1 = {
            "message": "你叫什么名字？",
            "history": []
        }
        first_response_text = ""
        with requests.post(url, json=payload1, headers=headers, stream=True, timeout=30) as r1:
            self.assertEqual(r1.status_code, 200)
            for chunk in r1.iter_content(chunk_size=None):
                if chunk:
                    decoded_chunk = chunk.decode('utf-8')
                    if decoded_chunk.startswith("data:"):
                        content = decoded_chunk[len("data:"):].strip()
                        if content and content != "[END_OF_STREAM]" and not content.startswith("[ERROR]"):
                           first_response_text += content
        
        self.assertTrue(len(first_response_text) > 0, "第一轮回复不应为空")
        print(f"第一轮回复: {first_response_text}")

        # 第二轮，带上第一轮的历史
        history = [
            {"role": "user", "content": payload1["message"]},
            {"role": "assistant", "content": first_response_text}
        ]
        payload2 = {
            "message": "你喜欢编程吗？", # 基于第一轮的上下文提问
            "history": history
        }
        
        second_response_text = ""
        with requests.post(url, json=payload2, headers=headers, stream=True, timeout=30) as r2:
            self.assertEqual(r2.status_code, 200)
            chunk_count = 0
            for chunk in r2.iter_content(chunk_size=None):
                if chunk:
                    decoded_chunk = chunk.decode('utf-8')
                    if decoded_chunk.startswith("data:"):
                        content = decoded_chunk[len("data:"):].strip()
                        if content and content != "[END_OF_STREAM]" and not content.startswith("[ERROR]"):
                            second_response_text += content
                            chunk_count +=1
        
        print(f"第二轮回复: {second_response_text}")
        self.assertGreater(chunk_count, 0, "第二轮应至少收到一个数据块")
        self.assertTrue(len(second_response_text) > 0, "第二轮回复不应为空")
        # 理想情况下，第二轮的回复应该与上下文相关，但这很难自动化测试
        # 至少我们可以确认它有回复

    def test_04_chat_empty_message(self):
        """测试发送空消息时的错误处理"""
        url = BASE_URL + "/chat"
        payload = {
            # "message": "", // message 为空或缺失
            "history": []
        }
        headers = {'Content-Type': 'application/json'}
        
        # 情况1: message 字段缺失
        response_missing = requests.post(url, json=payload, headers=headers)
        self.assertEqual(response_missing.status_code, 400)
        json_data_missing = response_missing.json()
        self.assertIn("error", json_data_missing)
        self.assertEqual(json_data_missing["error"], "No message provided")

        # 情况2: message 字段为空字符串
        payload_empty_msg = {
            "message": "",
            "history": []
        }
        response_empty = requests.post(url, json=payload_empty_msg, headers=headers)
        self.assertEqual(response_empty.status_code, 400) # 假设后端对空message也返回400
        json_data_empty = response_empty.json()
        self.assertIn("error", json_data_empty)
        self.assertEqual(json_data_empty["error"], "No message provided") # 确保错误信息一致

    # 可以添加更多测试用例，例如测试模型回复特定类型问题的能力（如果可预测）
    # 或者测试一些边界条件

if __name__ == '__main__':
    # 重要: 确保你的 Flask app.py 正在运行，并且模型已加载
    # 你可能需要先手动启动它: python app.py
    print("正在运行功能测试... 请确保后端服务已启动并在 {}。".format(BASE_URL))
    print("如果模型较大，请等待模型加载完毕后再运行测试。")
    
    # 为了让测试按顺序执行（01, 02, ...），unittest.main() 默认按字母顺序
    # 如果确实需要严格顺序，可以自定义 TestLoader
    # loader = unittest.TestLoader()
    # loader.sortTestMethodsUsing = None # 或者 lambda x, y: cmp(x, y) for Python 2
    # suite = loader.loadTestsFromTestCase(ChatAppFunctionalTests)
    # runner = unittest.TextTestRunner()
    # runner.run(suite)
    # 但通常，测试应该是独立的，不依赖顺序。这里的命名只是为了可读性。
    unittest.main(verbosity=2)