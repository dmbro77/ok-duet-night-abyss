import WebSocket from 'ws';

// 定义发往 WebSocket 的命令
export const WsCommand = {
    SendText: (text) => ({ type: 'SendText', text }),
    Close: { type: 'Close' }
};

// 全局状态
const globalState = {
    wsTx: null,        // 发送指令的通道
    wsConfig: null,    // 配置信息
    wsClient: null,    // WebSocket 实例
    isRunning: false,  // 是否正在运行
    reconnectTimer: null, // 重连定时器
    heartbeatTimer: null, // 心跳定时器
    firstMessagePromise: null, // 第一条消息的 Promise
    firstMessageResolve: null, // 第一条消息的 resolve 函数
    firstMessageReject: null,  // 第一条消息的 reject 函数
};

/**
 * 初始化全局 WebSocket 客户端
 * @param {string} urlStr - 连接地址
 * @param {string} token - token
 * @param {string} userId - 用户 ID
 * @param {number} interval - 心跳间隔（秒）
 */
function initGlobalWs(urlStr, token, userId, interval) {
    // 创建第一条消息的 Promise
    globalState.firstMessagePromise = new Promise((resolve, reject) => {
        globalState.firstMessageResolve = resolve;
        globalState.firstMessageReject = reject;
    });

    // 创建指令通道（用简单的回调机制模拟）
    const commandEmitter = {
        listeners: [],
        send: function(command) {
            // 复制 listeners 避免在遍历时修改
            const listenersCopy = [...this.listeners];
            listenersCopy.forEach(listener => {
                try {
                    listener(command);
                } catch (error) {
                    console.error('[WS] Error in command listener:', error);
                }
            });
        },
        recv: function(callback) {
            this.listeners.push(callback);
        },
        removeListener: function(callback) {
            const index = this.listeners.indexOf(callback);
            if (index > -1) {
                this.listeners.splice(index, 1);
            }
        },
        close: function() {
            this.listeners = [];
        }
    };

    // 将发送端存入全局变量
    globalState.wsTx = commandEmitter;

    // 保存配置信息
    globalState.wsConfig = { userId, token, url: urlStr, interval };

    // 启动 WebSocket 任务（不阻塞，在后台运行）
    startWebSocketTask(urlStr, token, userId, interval, commandEmitter);
    
    // 返回第一条消息的 Promise
    return globalState.firstMessagePromise;
}

/**
 * 启动 WebSocket 后台任务
 */
async function startWebSocketTask(urlStr, token, userId, interval, commandEmitter) {
    globalState.isRunning = true;
    let connectionAttempts = 0;
    let hasReceivedFirstMessage = false;
    
    // 保存当前任务的控制变量
    let currentTaskActive = true;
    
    // 定义一个清理函数
    const cleanupTask = () => {
        currentTaskActive = false;
        if (globalState.heartbeatTimer) {
            clearInterval(globalState.heartbeatTimer);
            globalState.heartbeatTimer = null;
        }
        if (globalState.wsClient) {
            try {
                globalState.wsClient.close();
            } catch (e) {
                // 忽略关闭错误
            }
            globalState.wsClient = null;
        }
    };

    while (globalState.isRunning && currentTaskActive) {
        try {
            connectionAttempts++;
            console.log(`[WS] Connecting to ${urlStr}... (attempt ${connectionAttempts})`);

            // 1. 构建带有自定义 Header 的请求
            const headers = {
                'token': token,
                'appVersion': '1.2.0',
                'sourse': 'android'
            };

            // 2. 建立连接
            const ws = new WebSocket(urlStr, { headers });
            globalState.wsClient = ws;
            
            // 重置第一条消息标志
            hasReceivedFirstMessage = false;
            
            // 等待连接建立
            const connectionPromise = new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    ws.close();
                    reject(new Error('Connection timeout'));
                }, 10000);

                ws.onopen = () => {
                    clearTimeout(timeout);
                    console.log('[WS] Connected!');
                    resolve();
                };

                ws.onerror = (error) => {
                    clearTimeout(timeout);
                    console.error('[WS] Connection error:', error.message || error);
                    reject(error);
                };
            });

            await connectionPromise;
            
            // 重置连接尝试计数
            connectionAttempts = 0;
            
            // 3. 设置消息处理器
            const messageHandler = (event) => {
                try {
                    const text = event.data.toString();
                    console.log('[WS] Received Text:', text);

                    // 尝试解析消息
                    let response;
                    try {
                        response = JSON.parse(text);
                    } catch (e) {
                        console.error('[WS] Failed to parse message as JSON:', e);
                        return;
                    }

                    // 如果是第一条消息，处理 firstMessagePromise
                    if (!hasReceivedFirstMessage && globalState.firstMessageResolve) {
                        hasReceivedFirstMessage = true;
                        console.log('[WS] First message received');
                        
                        // 返回 data 字段，如果没有 data 字段则返回空字符串
                        const data = response.data !== undefined ? response.data : '';
                        globalState.firstMessageResolve(data);
                        
                        // 清空引用，避免内存泄漏
                        globalState.firstMessageResolve = null;
                        globalState.firstMessageReject = null;
                    }

                    // 处理其他类型的消息
                    // 这里可以根据需要添加业务逻辑
                    console.log('[WS] Message processed, code:', response.code);

                } catch (error) {
                    console.error('[WS] Error processing message:', error);
                }
            };

            ws.onmessage = messageHandler;

            // 4. 设置心跳定时器
            if (globalState.heartbeatTimer) {
                clearInterval(globalState.heartbeatTimer);
            }
            
            const heartbeatIntervalMs = interval * 1000;
            globalState.heartbeatTimer = setInterval(() => {
                if (ws.readyState === WebSocket.OPEN && globalState.isRunning) {
                    const pingMessage = JSON.stringify({
                        data: { userId: userId },
                        event: "ping"
                    });
                    
                    try {
                        ws.send(pingMessage);
                        console.log('[WS] Ping sent:', pingMessage);
                    } catch (error) {
                        console.error('[WS] Failed to send ping:', error);
                    }
                }
            }, heartbeatIntervalMs);

            // 5. 处理指令通道
            const commandHandler = (command) => {
                if (!globalState.isRunning || ws.readyState !== WebSocket.OPEN) {
                    return;
                }
                
                if (command.type === 'SendText') {
                    try {
                        ws.send(command.text);
                        console.log('[WS] Sent text:', command.text);
                    } catch (error) {
                        console.error('[WS] Failed to send text:', error);
                    }
                } else if (command.type === 'Close') {
                    console.log('[WS] Closing connection by command...');
                    cleanupTask();
                    // 不 break 循环，因为 isRunning 会被设为 false
                }
            };
            
            commandEmitter.recv(commandHandler);

            // 6. 等待连接关闭
            const closePromise = new Promise((resolve) => {
                const closeHandler = () => {
                    console.log('[WS] Connection closed');
                    commandEmitter.removeListener(commandHandler);
                    ws.removeEventListener('message', messageHandler);
                    resolve();
                };
                
                ws.onclose = closeHandler;
                ws.onerror = (error) => {
                    console.error('[WS] WebSocket error:', error.message || error);
                    closeHandler();
                };
            });

            await closePromise;
            
            // 清理当前连接的资源
            commandEmitter.removeListener(commandHandler);
            if (globalState.heartbeatTimer) {
                clearInterval(globalState.heartbeatTimer);
                globalState.heartbeatTimer = null;
            }

            // 如果不是主动关闭，则等待重连
            if (globalState.isRunning && currentTaskActive) {
                const delay = Math.min(5000 * Math.pow(1.5, connectionAttempts - 1), 30000);
                console.log(`[WS] Reconnecting in ${delay/1000} seconds...`);
                await sleep(delay);
            }

        } catch (error) {
            console.error('[WS] Connection failed:', error.message || error);
            
            // 如果是第一次连接失败，拒绝 firstMessagePromise
            if (!hasReceivedFirstMessage && globalState.firstMessageReject) {
                globalState.firstMessageReject(error);
                globalState.firstMessageResolve = null;
                globalState.firstMessageReject = null;
            }
            
            if (!globalState.isRunning || !currentTaskActive) {
                break;
            }
            
            // 等待重连
            const delay = Math.min(5000 * Math.pow(1.5, connectionAttempts - 1), 30000);
            console.log(`[WS] Reconnecting in ${delay/1000} seconds...`);
            await sleep(delay);
        }
    }
    
    console.log('[WS] WebSocket task ended');
}

/**
 * 公共API：发送消息
 * @param {string} text - 要发送的文本
 */
export function sendWsMsg(text) {
    if (globalState.wsTx) {
        globalState.wsTx.send(WsCommand.SendText(text));
    } else {
        console.error('WS Client not initialized yet!');
    }
}

/**
 * 启动心跳
 * @param {string} url - WebSocket URL
 * @param {string} token - 认证 token
 * @param {string} userId - 用户 ID
 * @param {number} interval - 心跳间隔（秒）
 * @returns {Promise<string>} 第一条消息的 data 值
 */
export async function startHeartbeat(url, token, userId, interval) {
    try {
        // 检查是否已存在 WebSocket 客户端
        const needRestart = globalState.isRunning;

        if (needRestart) {
            console.log('[WS] Existing client found, closing...');

            // 停止当前连接
            globalState.isRunning = false;
            
            // 发送关闭指令
            if (globalState.wsTx) {
                globalState.wsTx.send(WsCommand.Close);
            }

            // 清理资源
            cleanupResources();
            
            // 拒绝未完成的第一条消息 Promise
            if (globalState.firstMessageReject) {
                globalState.firstMessageReject(new Error('Connection restarted'));
            }
            
            // 重置 firstMessagePromise
            globalState.firstMessagePromise = null;
            globalState.firstMessageResolve = null;
            globalState.firstMessageReject = null;

            // 短暂延迟，确保旧连接完全关闭
            await sleep(500);
        }

        // 初始化全局 WebSocket 客户端
        const firstMessagePromise = initGlobalWs(url, token, userId, interval);
        
        // 设置超时
        const timeoutPromise = new Promise((_, reject) => {
            setTimeout(() => {
                reject(new Error('Timeout waiting for first message'));
            }, 30000); // 30秒超时
        });
        
        // 等待第一条消息或超时
        const firstMessage = await Promise.race([firstMessagePromise, timeoutPromise]);
        return firstMessage;

    } catch (error) {
        console.error('[WS] Failed to start heartbeat:', error.message || error);
        throw new Error('Failed to start heartbeat: ' + error.message);
    }
}

/**
 * 停止心跳
 * @returns {Promise<void>}
 */
export async function stopHeartbeat() {
    try {
        console.log('[WS] Stopping heartbeat...');
        
        // 设置运行标志为 false
        globalState.isRunning = false;
        
        // 发送关闭指令
        if (globalState.wsTx) {
            globalState.wsTx.send(WsCommand.Close);
        }
        
        // 清理资源
        cleanupResources();
        
        // 拒绝未完成的第一条消息 Promise
        if (globalState.firstMessageReject) {
            globalState.firstMessageReject(new Error('Connection stopped'));
        }
        
        // 重置所有状态
        resetGlobalState();
        
        console.log('[WS] Heartbeat stopped successfully');
        
    } catch (error) {
        console.error('[WS] Failed to stop heartbeat:', error);
        throw new Error('Failed to stop heartbeat: ' + error.message);
    }
}

/**
 * 清理资源
 */
function cleanupResources() {
    // 清理定时器
    if (globalState.heartbeatTimer) {
        clearInterval(globalState.heartbeatTimer);
        globalState.heartbeatTimer = null;
    }
    
    if (globalState.reconnectTimer) {
        clearTimeout(globalState.reconnectTimer);
        globalState.reconnectTimer = null;
    }
    
    // 关闭 WebSocket 连接
    if (globalState.wsClient) {
        try {
            globalState.wsClient.close();
        } catch (e) {
            // 忽略关闭错误
        }
        globalState.wsClient = null;
    }
    
    // 关闭命令通道
    if (globalState.wsTx) {
        globalState.wsTx.close();
    }
}

/**
 * 重置全局状态
 */
function resetGlobalState() {
    globalState.wsTx = null;
    globalState.wsConfig = null;
    globalState.wsClient = null;
    globalState.isRunning = false;
    globalState.reconnectTimer = null;
    globalState.heartbeatTimer = null;
    globalState.firstMessagePromise = null;
    globalState.firstMessageResolve = null;
    globalState.firstMessageReject = null;
}

/**
 * 工具函数：睡眠
 * @param {number} ms - 毫秒数
 * @returns {Promise<void>}
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 获取当前 WebSocket 状态
 * @returns {Object} 状态信息
 */
export function getWsStatus() {
    return {
        isRunning: globalState.isRunning,
        isConnected: globalState.wsClient && globalState.wsClient.readyState === WebSocket.OPEN,
        config: globalState.wsConfig,
        readyState: globalState.wsClient ? globalState.wsClient.readyState : null
    };
}

// // 导出模块
// module.exports = {
//     startHeartbeat,
//     stopHeartbeat,
//     sendWsMsg,
//     getWsStatus,
//     WsCommand
// };

// // 测试代码
// async function test() {
//     console.log('Starting WebSocket client test...');
    
//     try {
//         // 启动心跳
//         console.log('Calling startHeartbeat...');
//         const firstMessage = await startHeartbeat(
//             'wss://your-server.com/ws',
//             'your-token',
//             'user123',
//             30
//         );
        
//         console.log('First message received:', firstMessage);
//         console.log('startHeartbeat completed, continuing execution...');
        
//         // 继续执行其他代码
//         console.log('Sending test message...');
//         sendWsMsg(JSON.stringify({ event: 'test', data: 'Hello from test' }));
        
//         // 等待一段时间
//         await sleep(5000);
        
//         console.log('Stopping heartbeat...');
//         await stopHeartbeat();
        
//         console.log('Test completed successfully!');
        
//     } catch (error) {
//         console.error('Test failed:', error.message || error);
//     }
// }

// 如果要运行测试，取消注释下面这行
// test().catch(console.error);