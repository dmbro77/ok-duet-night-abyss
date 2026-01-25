import { DNAAPI } from 'dna-api';
import { startHeartbeat, stopHeartbeat } from './ws.js';

class DNAAPIWrapper {

  /**
   * 可以从dna builder获取到的user对象
   * @param {*} user {
        uid: uid || userId,
        name: name || userName,
        dev_code: dev_code,
        token: token,
        kf_token: kf_token || "",
        refreshToken: refreshToken,
        pic: pic || headUrl,
        status: status,
        isComplete: isComplete,
    }
   */
  constructor(user) {
    if (DNAAPIWrapper.instance) {
      return DNAAPIWrapper.instance;
    }
    DNAAPIWrapper.instance = this;

    this.apiCache = null;
    this.apiCacheKey = null;
    this.apiInitPromise = null;
    this.user = user;

    this.mihanUpdateTime = 0;
    this.mihanData = [];

    this.watch = false;

    
  }

  getCurrentUser() {
    return this.user;
  }

  async getDNAAPI() {
    const user = this.getCurrentUser();
    if (!user || !user.uid || !user.token || !user.refreshToken || !user.dev_code) {
      this.stopHeartbeat();
      return undefined;
    }

    // 检查缓存是否有效
    if (this.apiCache && this.apiCacheKey === user.uid) {
      return this.apiCache;
    }

    // 如果已有初始化Promise，直接返回
    if (this.apiInitPromise) {
      return await this.apiInitPromise;
    }

    // 创建新的初始化Promise
    this.apiInitPromise = (async () => {
      try {
        const api = new DNAAPI({
          dev_code: user.dev_code,
          token: user.token,
          kf_token: user.kf_token,
          debug: false,
          mode: 'android',
        });
        const res = await api.loginLog();
        if (res.msg.includes('失效')) {
          const refreshRes = await api.refreshToken(user.refreshToken);
          if (refreshRes.is_success && refreshRes.data?.token) {
            api.token = refreshRes.data.token;
            this.user.token = refreshRes.data.token;
          }
        }

        console.log('登录成功:', res);

        // 更新缓存
        this.apiCache = api;
        this.apiCacheKey = user.uid;

        // 启动心跳计时器
        await this.startHeartbeat(user.uid, user.token);

        return api;
      } catch (error) {
        console.error('获取DNAAPI失败:', error);
        return undefined;
      } finally {
        // 清除初始化Promise，允许下次重新初始化
        this.apiInitPromise = null;
      }
    })();

    return await this.apiInitPromise;
  }


  async getMihanData() {
    await this.updateMihanData();
    return this.mihanData;
  }

  // 启动心跳计时器
  async startHeartbeat(userId, token) {
    if (!userId || !token) {
      const user = this.getCurrentUser();
      if (!user) return false;
      userId = user.uid;
      token = user.token;
    }
    try {
      // 调用Rust实现的心跳功能
      const res = await startHeartbeat(
        'wss://dnabbs-api.yingxiong.com:8180/ws-community-websocket',
        token,
        userId,
        10
      );
      if (res.includes('成功')) {
        return true;
      } else {
        await stopHeartbeat();
      }
    } catch (error) {
      console.error('启动心跳失败:', error);
    }
    return false;
  }

  // 停止心跳计时器
  async stopHeartbeat() {
    try {
      // 调用Rust实现的停止心跳功能
      await stopHeartbeat();
      console.log('心跳已停止');
    } catch (error) {
      console.error('停止心跳失败:', error);
    }
  }

  async saveKFToken(token) {
    const user = this.getCurrentUser();
    if (!user) return;
    this.user.kf_token = token;
  }

  async updateMihanData() {
    const api = await this.getDNAAPI();
    if (api) {
      
      const user = this.getCurrentUser();
      // 用户登录尝试使用DNAAPI获取密函
      await this.startHeartbeat(user.uid, user.token);
      const data = await api.defaultRoleForTool();
      if (data?.data?.instanceInfo) {
        const missions = data.data.instanceInfo.map((v) =>
          v.instances.map((v) => v.name.replace('勘探/无尽', '勘察/无尽')),
        );
        if (!missions) return false;
        if (JSON.stringify(missions) === JSON.stringify(this.mihanData)) {
          this.mihanUpdateTime = Date.now();
          return false;
        }
        this.mihanData = missions;
        this.mihanUpdateTime = Date.now();
        return true;
      }else{
        console.log('获取密函失败1:', data);
        return false;
      }
    }else{
      console.log('获取密函失败2:获取api失败' );
      return false;
    }
  }

  getNextUpdateTime(t) {
    const now = t ?? Date.now();
    const oneHour = 60 * 60 * 1000;
    return Math.ceil(now / oneHour) * oneHour;
  }

  startWatch() {
    if (this.watch) return;
    console.log('start watch');
    this.watch = true;
    const next = this.getNextUpdateTime();
    const duration = next - Date.now();
    setTimeout(async () => {
      this.watch = false;
      let ok = await this.updateMihanData();
      let c = 0;
      while (!ok && c < 3) {
        c++;
        console.log('update mihan data failed, retry in 3s');
        ok = await this.updateMihanData();
        await this.sleep(3e3);
      }
      this.startWatch();
    }, duration + 25e3); // 由于服务器往往需要25s左右才能更新数据，所以这里设置25s
  }
}

export default DNAAPIWrapper;
