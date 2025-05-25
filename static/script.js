// static/script.js
document.addEventListener('DOMContentLoaded', () => {
    const chatBox = document.getElementById('chat-box');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const originalButtonText = sendButton.textContent; // 保存按钮原始文本
    let chatHistory = [];

    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = userInput.scrollHeight + 'px';
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
        
        const textNode = document.createTextNode(text);
        messageDiv.appendChild(textNode);
        
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
        return messageDiv;
    }

    function setButtonLoading(isLoading) {
        if (isLoading) {
            sendButton.disabled = true;
            sendButton.textContent = '生成中...'; // 或者使用 spinner 图标
            // 可以添加一个 CSS class 来改变样式，例如:
            sendButton.classList.add('loading');
        } else {
            sendButton.disabled = false;
            sendButton.textContent = originalButtonText;
            sendButton.classList.remove('loading');
        }
    }

    async function sendMessage() {
        const messageText = userInput.value.trim();
        if (messageText === '' || sendButton.disabled) return; // 如果按钮已禁用，则不执行

        appendMessage(messageText, 'user');
        chatHistory.push({ role: "user", content: messageText });
        userInput.value = '';
        userInput.style.height = 'auto';
        
        setButtonLoading(true); // <--- 禁用按钮并显示加载状态

        let botMessageDiv = appendMessage('', 'bot');
        botMessageDiv.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    message: messageText,
                    history: chatHistory
                }),
            });

            if (!response.ok) {
                let errorText = `服务器错误: ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorText = errorData.error || errorText;
                } catch (e) {
                    errorText = await response.text() || errorText;
                }
                console.error('Error from server:', errorText);
                botMessageDiv.textContent = `错误: ${errorText}`;
                // chatHistory.pop(); // 考虑是否移除，取决于错误类型
                return; // 在 finally 中恢复按钮
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullBotResponse = "";
            botMessageDiv.innerHTML = ""; 

            while (true) {
                const { value, done } = await reader.read();
                if (done) {
                    break;
                }
                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.substring(6).trim();
                        if (data === "[END_OF_STREAM]") {
                            // stream ended
                        } else if (data.startsWith("[ERROR]")) {
                            botMessageDiv.textContent += data.substring(7).trim();
                            fullBotResponse += data.substring(7).trim();
                        } else {
                            botMessageDiv.textContent += data;
                            fullBotResponse += data;
                            chatBox.scrollTop = chatBox.scrollHeight;
                        }
                    }
                }
            }
            if (fullBotResponse) {
                chatHistory.push({ role: "assistant", content: fullBotResponse });
            } else {
                chatBox.removeChild(botMessageDiv);
            }

        } catch (error) {
            console.error('Error sending message:', error);
            botMessageDiv.textContent = '发生网络错误，请稍后再试。';
        } finally {
            setButtonLoading(false); // <--- 在 finally 块中恢复按钮状态
        }
    }
});