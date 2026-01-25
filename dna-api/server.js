// 处理 __dirname 在打包后的路径问题
if (typeof process.pkg !== 'undefined') {
  __dirname = require('path').dirname(process.execPath);
}

import express from 'express';
import DNAAPIWrapper  from './dna-api-wrapper.js';

const app = express();
const PORT = 5644;

// 中间件：解析 JSON 请求体
app.use(express.json());
// 中间件：解析 URL 编码的数据
app.use(express.urlencoded({ extended: true }));


app.post('/getInstanceInfo', async (req, res) => {
  const { uid, token, refreshToken, dev_code } = req.body;
  if (!uid || !token || !refreshToken || !dev_code) {
    return res.status(400).json({
      code: 400,
      message: '缺少必要参数',
      data: null
    });
  }
  const dnaAPIWrapper = new DNAAPIWrapper({uid, token, refreshToken, dev_code});
  const instanceInfo = await dnaAPIWrapper.getMihanData();
  res.json({
    code: 200,
    message: '成功',
    data: instanceInfo
  });
});



// 错误处理中间件
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({
    code: 500,
    message: '服务器内部错误',
    data: null
  });
});

// 404 处理
app.use((req, res) => {
  res.status(404).json({
    code: 404,
    message: '接口不存在',
    data: null
  });
});

// 启动服务器
app.listen(PORT, () => {
  console.log(`服务器运行在 http://localhost:${PORT}`);
});

// 处理优雅关闭
process.on('SIGINT', () => {
  console.log('\n🛑 正在关闭服务器...');
  process.exit(0);
});