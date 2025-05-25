// static/script.js
document.addEventListener('DOMContentLoaded', () => {
    const chatBox = document.getElementById('chat-box');
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    // const originalButtonContent = sendButton.innerHTML; // 如果按钮内容是复杂HTML (例如SVG)
    let chatHistory = [];

    // 如果初始欢迎消息由JS添加 (可选，HTML中已静态添加了一个)
    // appendMessage("你好！我是您的智能聊天助手，有什么可以帮助您的吗？", 'bot', true);

    userInput.addEventListener('input', autoGrowTextarea);
    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });

    function autoGrowTextarea() {
        userInput.style.height = 'auto'; // Reset height
        const newHeight = Math.min(userInput.scrollHeight, parseInt(getComputedStyle(userInput).maxHeight));
        userInput.style.height = newHeight + 'px';
    }

    function appendMessage(text, sender, isWelcome = false) {
        const messageWrapper = document.createElement('div');
        messageWrapper.classList.add('message', sender === 'user' ? 'user-message' : 'bot-message');

        const avatarDiv = document.createElement('div');
        avatarDiv.classList.add('avatar', sender === 'user' ? 'user-avatar' : 'bot-avatar');
        avatarDiv.textContent = sender === 'user' ? '我' : 'AI'; // 简单的头像文字

        const messageContentDiv = document.createElement('div');
        messageContentDiv.classList.add('message-content');

        // 简单的文本处理，可以扩展为 Markdown 解析
        // 注意：直接用 innerHTML 插入用户输入或模型输出的原始文本存在XSS风险。
        // 在实际生产中，对于模型输出，如果需要渲染HTML (如Markdown转HTML)，务必使用安全的库并进行净化。
        // 对于纯文本，createTextNode 是安全的。
        if (sender === 'bot' && text.includes('<div class="typing-indicator">')) {
             messageContentDiv.innerHTML = text; // 允许打字指示器HTML
        } else {
            const p = document.createElement('p');
            p.textContent = text;
            messageContentDiv.appendChild(p);
        }
        
        messageWrapper.appendChild(avatarDiv);
        messageWrapper.appendChild(messageContentDiv);
        chatBox.appendChild(messageWrapper);
        
        // 只有在非欢迎消息或用户主动发送消息时才滚动到底部
        if (!isWelcome || sender === 'user') {
            chatBox.scrollTop = chatBox.scrollHeight;
        }
        return messageContentDiv; // 返回内容元素，用于流式更新或打字指示器
    }

    function setButtonLoading(isLoading) {
        sendButton.disabled = isLoading;
        if (isLoading) {
            sendButton.classList.add('loading');
            // sendButton.innerHTML = ''; // 清空SVG，让CSS ::after 生效 (如果用CSS spinner)
        } else {
            sendButton.classList.remove('loading');
            // sendButton.innerHTML = originalButtonContent; // 恢复SVG
        }
        // 注意：如果按钮内容是固定的SVG，通过CSS控制显示/隐藏SVG和spinner会更干净。
        // CSS中已通过 #send-button.loading svg { display: none; } 和 ::after 实现。
    }


    async function sendMessage() {
        const messageText = userInput.value.trim();
        if (messageText === '' || sendButton.disabled) return;

        // 用户消息也使用新的 appendMessage 结构
        appendMessage(messageText, 'user'); 
        chatHistory.push({ role: "user", content: messageText });
        userInput.value = '';
        autoGrowTextarea(); // 重置输入框高度
        
        setButtonLoading(true);

        // 为机器人回复创建一个占位符消息体 (只创建内容部分)
        const botMessageContentDiv = appendMessage('', 'bot'); // appendMessage 现在返回 messageContentDiv
        botMessageContentDiv.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';


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

            // 清空打字指示器，准备接收真实内容
            botMessageContentDiv.innerHTML = ""; 
            let fullBotResponse = "";

            if (!response.ok) {
                // ... (错误处理部分与之前类似, 但更新到 botMessageContentDiv.firstChild or create p) ...
                let errorText = `服务器错误: ${response.status}`;
                try { const errorData = await response.json(); errorText = errorData.error || errorText; }
                catch (e) { errorText = await response.text() || errorText; }
                
                const p = document.createElement('p');
                p.textContent = `错误: ${errorText}`;
                botMessageContentDiv.appendChild(p);
                console.error('Error from server:', errorText);
                return;
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            // 为流式内容创建一个<p>标签
            let currentParagraph = document.createElement('p');
            botMessageContentDiv.appendChild(currentParagraph);

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.substring(6).trim();
                        if (data === "[END_OF_STREAM]") { /* stream ended */ }
                        else if (data.startsWith("[ERROR]")) {
                            currentParagraph.textContent += data.substring(7).trim(); // 追加到p标签
                            fullBotResponse += data.substring(7).trim();
                        } else {
                            // 处理换行符：如果模型输出 \n，我们应该创建新的 <p> 或 <br>
                            // 这里简单处理，直接追加。如果模型能生成 markdown，后续可以增强。
                            currentParagraph.textContent += data; // 追加到p标签
                            fullBotResponse += data;
                            chatBox.scrollTop = chatBox.scrollHeight;
                        }
                    }
                }
            }

            if (fullBotResponse) {
                chatHistory.push({ role: "assistant", content: fullBotResponse });
            } else { 
                // 如果机器人没有回复内容，移除空的消息气泡
                if (botMessageContentDiv.parentNode && botMessageContentDiv.textContent.trim() === "") {
                     chatBox.removeChild(botMessageContentDiv.parentNode); // 移除整个 .message 元素
                }
            }

        } catch (error) {
            console.error('Error sending message:', error);
            if (botMessageContentDiv) { // 确保 botMessageContentDiv 存在
                botMessageContentDiv.innerHTML = ""; // 清空可能存在的打字指示器
                const p = document.createElement('p');
                p.textContent = '发生网络错误，请稍后再试。';
                botMessageContentDiv.appendChild(p);
            }
        } finally {
            setButtonLoading(false);
        }
    }
    
    // 初始化时调整一次输入框高度
    autoGrowTextarea();
});