# chatbot_app/app.py
import os
import threading
from flask import Flask, render_template, request, Response, stream_with_context, jsonify
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer, GenerationConfig
import torch

# --- 配置 ---
MODEL_PATH = os.path.join(
    ".", "Qwen1.5-1.8B-Chat_model", "models--Qwen--Qwen1.5-1.8B-Chat", 
    "snapshots", "e482ee3f73c375a627a16fdf66fd0c8279743ca6"
)
# 确保模型路径正确，如果你的脚本在 chatbot_app 目录下运行，上面的路径是正确的
# 如果你在 chatbot_app 的父目录运行 python chatbot_app/app.py, 则路径应相应调整或使用绝对路径

# --- 全局变量 ---
model = None
tokenizer = None
device = "cpu" # 明确使用CPU

# --- 应用创建函数 ---
def create_app():
    app = Flask(__name__)

    # --- 模型加载 ---
    def load_model():
        global model, tokenizer
        print(f"Loading model from: {MODEL_PATH}")
        try:
            tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_PATH,
                torch_dtype="auto", #可以尝试 torch.float32 如果 "auto" 有问题
                device_map=device, # 指定使用CPU
                trust_remote_code=True
            )
            model.eval() # 设置为评估模式
            print("Model loaded successfully on CPU.")
        except Exception as e:
            print(f"Error loading model: {e}")
            # 实际应用中可能需要更健壮的错误处理
            raise

    load_model() # 应用启动时加载模型

    # --- 路由 ---
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/chat', methods=['POST'])
    def chat():
        try:
            data = request.json
            user_input = data.get('message')
            history = data.get('history', []) # 接收聊天历史

            if not user_input:
                return jsonify({"error": "No message provided"}), 400

            messages = []
            for entry in history:
                messages.append({"role": entry["role"], "content": entry["content"]})
            messages.append({"role": "user", "content": user_input})
            
            # 使用 apply_chat_template 构建输入
            # Qwen1.5-Chat 的模板会自动处理多轮对话格式
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True # 重要：为模型生成添加起始提示
            )
            
            model_inputs = tokenizer([text], return_tensors="pt").to(device)

            streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
            
            generation_config = GenerationConfig(
                max_new_tokens=1024,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                repetition_penalty=1.05,
                # streamer=streamer, # streamer参数在generate调用时传入
                # eos_token_id=tokenizer.eos_token_id # Qwen1.5可能不需要显式设置这个
            )
            
            # generation_kwargs 用于传递给 generate 方法
            generation_kwargs = {
                "input_ids": model_inputs.input_ids,
                "attention_mask": model_inputs.attention_mask,
                "generation_config": generation_config,
                "streamer": streamer,
            }

            # 在一个单独的线程中运行生成，以允许流式处理
            thread = threading.Thread(target=model.generate, kwargs=generation_kwargs)
            thread.start()

            def generate_responses():
                for new_text in streamer:
                    yield f"data: {new_text}\n\n" # SSE格式
                # 可选：发送一个特殊的结束标记
                # yield f"data: [END_OF_STREAM]\n\n"

            return Response(stream_with_context(generate_responses()), mimetype='text/event-stream')

        except Exception as e:
            print(f"Error during chat generation: {e}")
            # 在流式传输中，错误处理比较棘手，这里简单打印
            # 可以考虑发送一个错误事件给客户端
            def error_stream():
                yield f"data: [ERROR] An error occurred: {str(e)}\n\n"
            return Response(stream_with_context(error_stream()), mimetype='text/event-stream', status=500)

    return app

# --- 主程序入口 ---
if __name__ == '__main__':
    app = create_app()
    # 修改端口避免与常见端口冲突，debug=True 用于开发
    app.run(host='0.0.0.0', port=5001, debug=True)