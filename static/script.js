document.addEventListener('DOMContentLoaded', () => {
    const chatBox = document.getElementById('chat-box');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    let chatHistory = []; // 用于存储对话历史

    // 调整textarea高度
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto'; // Reset height
        userInput.style.height = userInput.scrollHeight + 'px'; // Set to scroll height
    });

    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });

    function appendMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender === 'user' ? 'user-message' : 'bot-message');
        
        // 为了安全，对文本进行转义 (简单实现，实际应用可能需要更完善的库)
        const textNode = document.createTextNode(text);
        messageDiv.appendChild(textNode);
        
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight; // 滚动到底部
        return messageDiv; // 返回消息元素，用于流式更新
    }

    async function sendMessage() {
        const messageText = userInput.value.trim();
        if (messageText === '') return;

        appendMessage(messageText, 'user');
        chatHistory.push({ role: "user", content: messageText });
        userInput.value = '';
        userInput.style.height = 'auto'; // Reset height after sending
        sendButton.disabled = true; // 禁用发送按钮，直到收到回复

        // 为机器人回复创建一个占位符
        let botMessageDiv = appendMessage('', 'bot');
        // 可以添加一个打字指示器
        botMessageDiv.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';


        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    message: messageText,
                    history: chatHistory // 发送包含当前消息的完整历史
                }),
            });

            if (!response.ok) {
                // 如果HTTP状态码不是2xx，尝试读取错误信息
                let errorText = `服务器错误: ${response.status}`;
                try {
                    const errorData = await response.json(); // 假设服务器返回JSON错误
                    errorText = errorData.error || errorText;
                } catch (e) {
                    // 如果响应不是JSON或解析失败
                    errorText = await response.text() || errorText;
                }
                console.error('Error from server:', errorText);
                botMessageDiv.textContent = `错误: ${errorText}`;
                chatHistory.pop(); // 如果发送失败，从历史中移除用户最后一条消息
                sendButton.disabled = false;
                return;
            }
            
            // 使用 ReadableStream 处理流式响应
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullBotResponse = "";
            botMessageDiv.innerHTML = ""; // 清除打字指示器

            while (true) {
                const { value, done } = await reader.read();
                if (done) {
                    break;
                }
                const chunk = decoder.decode(value, { stream: true });
                // SSE 数据格式是 "data: content\n\n"
                // 我们需要解析出 content
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.substring(6).trim();
                        if (data === "[END_OF_STREAM]") { // 可选的结束标记
                            // stream ended
                        } else if (data.startsWith("[ERROR]")) {
                            botMessageDiv.textContent += data.substring(7).trim();
                            fullBotResponse += data.substring(7).trim();
                        } else {
                            botMessageDiv.textContent += data; // 逐字追加
                            fullBotResponse += data;
                            chatBox.scrollTop = chatBox.scrollHeight;
                        }
                    }
                }
            }
            // 流结束后，将完整的机器人回复添加到历史记录
            if (fullBotResponse) {
                chatHistory.push({ role: "assistant", content: fullBotResponse });
            } else { // 如果机器人没有回复任何内容（例如，只有错误或空流）
                chatBox.removeChild(botMessageDiv); // 移除空的机器人消息框
                // chatHistory.pop(); // 用户消息已添加，不需要移除
            }

        } catch (error) {
            console.error('Error sending message:', error);
            botMessageDiv.textContent = '发生网络错误，请稍后再试。';
            // chatHistory.pop(); // 移除用户消息，因为没有成功交互
        } finally {
            sendButton.disabled = false; // 重新启用发送按钮
        }
    }
});