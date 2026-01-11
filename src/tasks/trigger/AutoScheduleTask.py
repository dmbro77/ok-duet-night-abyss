import requests
from qfluentwidgets import FluentIcon
import time
import re
import win32api
import win32con
import random
from datetime import datetime

from ok import Logger, og, Box, TriggerTask
from src.tasks.CommissionsTask import CommissionsTask
from src.tasks.BaseCombatTask import BaseCombatTask

# 导入具体的任务类
from src.tasks.fullauto.AutoExploration_Fast import AutoExploration_Fast
from src.tasks.AutoExpulsion import AutoExpulsion
from src.tasks.fullauto.Auto65ArtifactTask_Fast import Auto65ArtifactTask_Fast
from src.tasks.fullauto.Auto70jjbTask import Auto70jjbTask
from src.tasks.fullauto.AutoEscortTask import AutoEscortTask
from src.tasks.fullauto.AutoEscortTask_Fast import AutoEscortTask_Fast
from src.tasks.fullauto.ImportTask import ImportTask
from src.tasks.fullauto.AutoDismantle import AutoDismantle

logger = Logger.get_logger(__name__)

class AutoScheduleTask(CommissionsTask, BaseCombatTask, TriggerTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动密函委托【有前台操作】"
        self.description = "整点自动检查密函任务并按照优先级匹配任务执行，未匹配到则执行默认任务\n1、需在历练->委托页面启动 2、需要停止其他正在运行的任务 3、需要设置好自动处理密函\n整点切换任务的时候会有延迟，6分钟以内属于正常"
        self.group_icon = FluentIcon.CAFE
        
        # 默认配置（仅保留业务配置）
        self.default_config = {
            # 模块优先级
            "密函委托优先级": '角色>武器>MOD',
            # 任务优先级
            "关卡类型优先级": '探险/无尽>驱离',
            # 默认任务配置
            "默认任务": "自动70级皎皎币本",
            "默认任务副本类型": "角色技能材料:扼守/无尽",
            "副本等级【普通任务】": "lv.70",
            "副本名称【夜航任务】": "霜狱野蜂暗箭",
        }
           # 默认任务映射
        self.DEFAULT_TASK_MAPPING = {
            "自动70级皎皎币本": Auto70jjbTask,
            "自动飞枪80护送（无需巧手）【需要游戏处于前台】": AutoEscortTask,
            "黎瑟：超级飞枪80护送": AutoEscortTask_Fast,
            "使用外部移动逻辑自动打本": ImportTask,
            "自动探险/无尽": AutoExploration_Fast,
            "自动驱离": AutoExpulsion,
            "自动30/65级魔之楔本": Auto65ArtifactTask_Fast,
        }

        self.config_type = {
            "默认任务": {
                "type": "drop_down",
                "options": list(self.DEFAULT_TASK_MAPPING.keys()),
            },
            "默认任务副本类型": {
                "type": "drop_down",
                 "options": [
                    "铜币:勘察无尽",
                    "角色经验:避险",
                    "武器经验:驱逐",
                    "角色突破材料:探险/无尽",
                    "武器突破材料:调停",
                    "魔之楔:驱离",
                    "深红凝珠:护送",
                    "角色技能材料:追缉",
                    "角色技能材料:扼守/无尽",
                    "铸造材料:迁移",
                    "夜航手册:20",
                    "夜航手册:30",
                    "夜航手册:40",
                    "夜航手册:50",
                    "夜航手册:55",
                    "夜航手册:60",
                    "夜航手册:65",
                    "夜航手册:70",
                    "夜航手册:80"
                ]
            },
            "副本等级【普通任务】": {
                "type": "drop_down",
                 "options": [
                    "lv.5", "lv.10", "lv.15", "lv.20", "lv.30", "lv.35", "lv.40", "lv.50", "lv.60", "lv.70", "lv.80", "lv.100",
                ]
            },
        }

        self.config_description = {
            "密函委托优先级": "使用 > 分隔优先级，越靠前优先级越高，只能填写角色、武器、MOD。\n例如：角色>武器>MOD",
            "关卡类型优先级": "使用 > 分隔优先级，越靠前优先级越高，仅支持探险/无尽、驱离、拆解。\n例如：探险/无尽>驱离>拆解",
            "默认任务": "当没有匹配的委托密函任务时，自动执行此任务\n任务基于已有的任务执行，请对设置的任务做好相应配置",
            "默认任务副本类型": "可选普通任务和夜航任务\n根据选择的默认任务进行设置即可",
            "副本等级【普通任务】": "副本类型为正常委托时生效\n选择需要刷取的副本等级，根据选择的默认任务和副本类型进行设置",
            "副本名称【夜航任务】": "副本类型为夜航手册时生效\n填写需要刷取的夜航手册名称，根据选择的默认任务和副本类型进行设置\n列如：霜狱野蜂暗箭(不需要空格)，如果匹配不到，可以填写部分名称",
        }

        # 任务映射关系
        self.TASK_MAPPING = {
            "探险/无尽": AutoExploration_Fast,
            "驱离": AutoExpulsion,
            "拆解": AutoDismantle,
        }
        
        # 调度器核心状态
        self.init_param()

    def _log_info(self, msg):
        if self.last_scheduled_task:
            self.last_scheduled_task.info_set('自动密函log',msg)
        else:    
         self.log_info(msg) 

    def scroll_relative(self, x, y, delta):
        # 保持原有的滚动逻辑
        try:
            abs_pos = og.device_manager.hwnd_window.get_abs_cords(
                self.width_of_screen(x),
                self.height_of_screen(y)
            )
            
            self.try_bring_to_front()
            
            win32api.SetCursorPos(abs_pos)
            self.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 0, 0, 0)
            self.sleep(0.05)
            target_wheel_delta = -int(delta)
            self._log_info(f"scroll_relative: pos={abs_pos}, input_delta={delta}, wheel_delta={target_wheel_delta}")

            step_size = 120
            if target_wheel_delta < 0:
                step_size = -120
                
            current_delta = 0
            while abs(current_delta) < abs(target_wheel_delta):
                remaining = target_wheel_delta - current_delta
                if abs(remaining) < abs(step_size):
                    step = remaining
                else:
                    step = step_size
                
                win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, step, 0)
                current_delta += step
                self.sleep(0.01)
                
        except Exception as e:
            self._log_info(f"win32 scroll failed: {e}")
    
    def init_param(self):
        """初始化"""
          # 调度器核心状态
        self.last_task_name = None  # 最后任务名称
        self.last_task_module = None  # 最后任务模块
        self.last_scheduled_task = None  # 最后一个任务

        self.finished_tasks = set()  # 已完成的任务标识（仅密函任务）
        self.finished_tasks.clear()
        self.task_stats = []  # 任务统计信息
        
        self.last_check_hour = -1  # 上次检查的小时
        self.last_api_response_data = None # 上次 API 返回的数据

        self.prev_task_is_force_stop = False  # 上一个任务是否被强制停止

    def enable(self):
        if self.enabled:
            return
        super().enable()
        self.init_param()
        self._log_info("调度任务已启动")
        self.thread_pool_executor.submit(self._scheduler_loop)

    def disable(self):
        super().disable()
        if self.last_scheduled_task:
            self.executor.stop_current_task()
        self.finished_tasks.clear()
        self._log_info("调度任务已停止")

    def is_enable_running(self):
        """检查当前是否可以运行"""
        return self.enabled and not self.executor.exit_event.is_set()
    

    def run(self):
        # 主线程轮询留空，因为逻辑在独立线程里
        return False

    def _validate_config(self):
        """验证必需配置"""
        required_configs = [
            "默认任务副本类型",
            "副本等级【普通任务】", 
            "副本名称【夜航任务】", 
            "默认任务",
            "密函委托优先级",
            "关卡类型优先级"
        ]
        
        for config_key in required_configs:
            if not self.config.get(config_key):
                self.info_set(f"自动密函：{config_key}", "未配置")
                return False
        
        return True
    
    def _scheduler_loop(self):
        """调度器主循环 - 仅负责检查统计"""
            
        def _check_and_update_completed_task():
            """检查并更新已完成的任务状态"""
            if self.last_scheduled_task is None:
                return True
                
            # 如果任务被禁用了（说明执行完成了，或者被手动停止了）
            if not self.last_scheduled_task.enabled:
                self._log_info(f"检测到任务 {self.last_scheduled_task.name} 已结束")
                
                # 更新任务统计信息
                self.task_stats[-1]["end_time"] = time.strftime("%H:%M:%S", time.localtime())
                self.task_stats[-1]["status"] = '任务自行完成'
                
                # 如果是密函任务且不是被强制停止（自行停止的任务需要添加），添加到已完成集合
                if self.last_task_module != "default" and not self.prev_task_is_force_stop:
                    task_key = f"{self.last_task_module}_{self.last_task_name}_{self.last_scheduled_task.__class__.__name__}"
                    self.finished_tasks.add(task_key)
                    self._log_info(f"密函任务完成，加入已执行列表: {task_key}")
                    # 重置状态
                    self.prev_task_is_force_stop = True
                
                self._update_task_summary_ui()
                self.last_scheduled_task = None
                return True
            return False
        
        def _should_trigger_hourly_check(now):
            """判断是否应该触发整点检查"""
            return (now.minute == 0 and 
                    now.second >= 10 and 
                    now.hour != self.last_check_hour)
        
        def _handle_scheduler_error():
            """处理调度器异常"""
            if self.task_stats[-1]["end_time"] is None:
                self.task_stats[-1]["end_time"] = time.strftime("%H:%M:%S", time.localtime())
                self.task_stats[-1]["status"] = f'异常关闭: {e}'
            self._update_task_summary_ui()
        
        def _cleanup_on_exit():
            """退出时清理"""
            if self.task_stats[-1]["end_time"] is None:
                self.task_stats[-1]["end_time"] = time.strftime("%H:%M:%S", time.localtime())
                self.task_stats[-1]["status"] = '手动关闭自动密函任务'
            self._update_task_summary_ui()


        # if self.executor.paused:
        #     self.executor.start()
        # a,b,c = self.get_letter_num()
        # self._log_info(f"当前密函数量: {a}个, {b}个, {c}个")
        # return

        if not self._validate_config():
            return
        self._log_info("调度器循环开始")
        
        # true 启动时立即检查一次
        should_check = True
        self.last_check_hour = datetime.now().hour
        while self.is_enable_running():
            try:
                # 确保执行器处于运行状态 (唤醒执行器)，否则OCR会卡住
                if self.executor.paused:
                    self.executor.start()
                    
                now = datetime.now()
                # 1. 检查已完成的任务并更新状态，返回是否需要执行标识
                should_check = _check_and_update_completed_task()
                
                # 2. 整点检查（必须的）
                if _should_trigger_hourly_check(now):
                    self._log_info(f"整点触发检查: {now.hour}:00")
                    time.sleep(random.randint(5, 20))  # 随机延时5-20秒，避免请求过于集中
                    should_check = True
            
                # 3. 执行检查
                if should_check:
                    task_class, module_key, task_name = self._calculate_target_task()
                    self.last_check_hour = now.hour
                    self.schedule_task(task_class, module_key, task_name)
                    self._update_task_summary_ui()
                    should_check = False
                    
                time.sleep(1)  # 等待1秒后继续
                
            except Exception as e:
                self._log_info(f"调度器循环异常: {e}")
                _handle_scheduler_error(e)
                time.sleep(10)  # 出错后等待10秒
        
        _cleanup_on_exit()
        self._log_info("调度线程循环结束")
 
    def _calculate_target_task(self):
        """计算得出最终可执行任务"""

        def _fetch_api_data(api_url, headers, max_retries=5):
            """获取API数据（内部函数）"""
            retries = 1
            while self.is_enable_running() and retries <= max_retries:
                params = {"_t": int(time.time() * 1000)}
                try:
                    response = requests.get(api_url, headers=headers, params=params, timeout=10)
                    response.raise_for_status()
                    json_data = response.json()
                    
                    if json_data.get("code") != 0 or not isinstance(current_data := json_data.get("data", []), list):
                        self._log_info(f"API返回错误代码: {json_data.get('code')}，或者data不是列表格式，{60*retries}s后重试 ({retries}/{max_retries})...")
                        if retries < max_retries:
                            time.sleep(60)
                        retries += 1
                        continue
                    self._log_info(f"API返回数据: {current_data}")
                    # 检查是否与上次数据相同
                    if _is_same_as_last_data(current_data):
                        self._log_info(f"API返回数据与上次相同，60s后重试 ({retries}/{max_retries})...")
                        if retries < max_retries:
                            time.sleep(60)
                        retries += 1
                        continue
                    
                    # 数据已更新
                    if self.last_api_response_data is not None:
                        self._log_info("API数据已更新")
                    self.last_api_response_data = current_data
                    return True
                    
                except Exception as req_err:
                    self._log_info(f"请求API失败 ({retries}): {req_err}")
                    if retries < max_retries:
                        time.sleep(60)
                    retries += 1
                    
            return False

        def _is_same_as_last_data(current_data):
            """检查数据是否与上次相同（内部函数）"""
            return (self.last_api_response_data is not None and 
                    current_data == self.last_api_response_data)

        def _get_sorted_tasks(instance_info_list):
            """获取排序后的任务列表（内部函数）"""
            # 解析优先级配置
            commission_config = self.config.get("密函委托优先级", "角色>武器>MOD")
            commission_order = [x.strip() for x in commission_config.split(">") if x.strip()]
            
            module_index_map = {"角色": 0, "武器": 1, "MOD": 2}
            sorted_modules = [name for name in commission_order if name in module_index_map]
            
            if not sorted_modules:
                self._log_info("未配置有效的密函委托优先级")
                return []

            # 解析关卡优先级
            level_config = self.config.get("关卡类型优先级", "探险/无尽>驱离>拆解")
            level_order = [x.strip() for x in level_config.split(">") if x.strip()]
            task_priority_map = {name: i for i, name in enumerate(level_order)}

            tasks_to_execute = []

            # 遍历模块寻找任务 - 先按密函委托优先级排序
            for module_key in sorted_modules:
                index = module_index_map.get(module_key)
                if index is None or index >= len(instance_info_list):
                    continue

                module_data_item = instance_info_list[index]
                module_instances = module_data_item.get("instances", [])
                
                if not module_instances:
                    continue

                for task_info in module_instances:
                    mapped_name = task_info.get("name") 
                    if mapped_name and mapped_name in self.TASK_MAPPING:
                        priority = task_priority_map.get(mapped_name, 999)
                        # 添加模块优先级作为主要排序键
                        module_priority = sorted_modules.index(module_key)
                        tasks_to_execute.append({
                            "name": mapped_name,
                            "class": self.TASK_MAPPING[mapped_name],
                            "priority": priority,
                            "module_key": module_key,
                            "module_priority": module_priority  # 添加模块优先级
                        })

            # 按优先级排序 - 先按模块优先级，再按关卡优先级
            tasks_to_execute.sort(key=lambda x: (x["module_priority"], x["priority"]))
            return tasks_to_execute

        def _find_first_executable_task(tasks_to_execute):
            """找到第一个可执行的任务（内部函数）"""
            # 获取密函数量
            rule_num, weapon_num, mod_num = self.get_letter_num()
            logger.debug(f"当前密函数量 - 角色: {rule_num}, 武器: {weapon_num}, MOD: {mod_num}")
            
            for task in tasks_to_execute:
                task_key = f"{task['module_key']}_{task['name']}_{task['class'].__name__}"
                
                # 检查密函数量
                if not _has_enough_letters(task['module_key'], rule_num, weapon_num, mod_num):
                    continue

                logger.debug(f"已完成任务: {self.finished_tasks}")    
                # 检查是否已完成
                if task_key not in self.finished_tasks:
                    self._log_info(f"匹配到任务: {task['name']} (模块: {task['module_key']})")
                    return task['class'], task['module_key'], task['name']
                    
            return None

        def _has_enough_letters(module_key, rule_num, weapon_num, mod_num):
            """检查是否有足够的密函（内部函数）"""
            if module_key == "角色" and rule_num == 0:
                self._log_info(f"角色任务 密函数量为0，跳过")
                return False
            if module_key == "武器" and weapon_num == 0:
                self._log_info(f"武器任务 密函数量为0，跳过")
                return False
            if module_key == "MOD" and mod_num == 0:
                self._log_info(f"MOD任务 密函数量为0，跳过")
                return False
            return True

        def _get_default_task_info():
            """获取默认任务信息"""
            default_task_name = self.config.get("默认任务")
            if default_task_name and default_task_name in self.DEFAULT_TASK_MAPPING:
                return self.DEFAULT_TASK_MAPPING[default_task_name], "default", default_task_name
            return None, None, default_task_name

        API_URL = "https://wiki.ldmnq.com/v1/dna/instanceInfo"
        HEADERS = {"game-alias": "dna"}
        
        try:
            self._log_info(f"请求API获取任务数据，小时信息：{self.last_check_hour}，{datetime.now().hour}，将最多执行{1 if self.last_check_hour == datetime.now().hour else 5}次")
            
            # 获取API数据
            if not _fetch_api_data(API_URL, HEADERS, 1 if self.last_check_hour == datetime.now().hour else 5):
                return _get_default_task_info()
                
            instance_info_list = self.last_api_response_data
            self._log_info(f"最终API数据: {instance_info_list}")
            
            # 获取任务列表并排序
            tasks_to_execute = _get_sorted_tasks(instance_info_list)
            self._log_info(f"api返回的可执行任务列表: {tasks_to_execute}")
            
            # 找到第一个可执行的任务
            result = _find_first_executable_task(tasks_to_execute)
            if result:
                return result
                
            self._log_info(f"已完成的任务: {self.finished_tasks}")
            self._log_info("未匹配到可执行的密函任务，执行默认任务")
            return _get_default_task_info()
            
        except Exception as e:
            self._log_info(f"请求API或处理数据失败: {e}")
            return _get_default_task_info()

    def schedule_task(self, task_class, module_key, task_name):
        """执行任务,如果当前有任务在运行,强制停止当前任务"""

        def _need_switch_task(target_task, module_key, task_name):
            """检查是否需要切换任务"""
            is_same_task = (
                self.last_task_module == module_key and
                self.last_task_name == task_name and
                isinstance(self.last_scheduled_task, target_task.__class__)
            )
            
            self._log_info(f"任务变化信息: {self.last_task_module}->{module_key}, "
                        f"{self.last_task_name}->{task_name}, "
                        f"{self.last_scheduled_task}->{target_task}")
            
            if is_same_task:
                self._log_info(f"任务相同且正在运行，无需切换: {task_name}")
                return False
            
            # 更新任务记录
            self.last_task_module = module_key
            self.last_task_name = task_name
            return True

        def _stop_current_task():
            """停止当前正在运行的任务"""
            current_task = self.executor.current_task
            if current_task is None:
                self._log_info(f"当前没有正在运行的任务，不需要停止")
                return
            
            self._log_info(f"正在强制停止当前任务: {current_task.name}")
            self.executor.stop_current_task()  # 发送停止信号
            
            # 等待当前任务退出 (最多等60秒)
            now_time = time.time()
            while time.time() - now_time < 60 and self.is_enable_running():
                if self.executor.current_task is None:
                    self.prev_task_is_force_stop = False
                    # 更新任务统计信息
                    self.task_stats[-1]["end_time"] = time.strftime("%H:%M:%S", time.localtime())
                    self.task_stats[-1]["status"] = '被调度停止'
                    break
                time.sleep(1)
            
            if self.executor.current_task is not None:
                raise Exception("当前任务停止超时")

        def _start_target_task( target_task, module_key, task_name):
            """启动目标任务"""
            if not target_task.enabled or self.executor.current_task is None:
                # 重置ui，回到历练页面
                self._reset_ui_state()

                self._log_info(f"正在启动任务: {self.last_task_module}-{self.last_task_name}")
                
                target_task.enable()
                self._log_info(f"任务 {self.last_task_name} 已启用，target_task.name=>{target_task.name}")
                self.go_to_tab(target_task.name)
                
                # 记录当前调度的任务，用于后续追踪完成状态
                self.last_scheduled_task = target_task
                self.task_stats.append({
                    "module_key": module_key,
                    "task_name": task_name,
                    "status": '运行中',
                    "start_time": time.strftime("%H:%M:%S", time.localtime()),
                    "end_time": None
                })
            else:
                self._log_info(f"任务 {self.last_task_name} 已经在运行中")
                # 记录当前调度的任务，用于后续追踪完成状态
                self.last_scheduled_task = target_task

        target_task = self.executor.get_task_by_class_name(task_class.__name__)

        if not target_task:
            self._log_info(f"未找到任务: {task_class.__name__}")
            return

        # 1. 检查是否需要切换任务
        if not _need_switch_task(target_task, module_key, task_name):
            return

        # 2 如果当前没有正在运行的任务，且有任务统计记录，更新任务统计信息
        if self.executor.current_task is None and self.task_stats:
            self.task_stats[-1]["end_time"] = time.strftime("%H:%M:%S", time.localtime())
            self.task_stats[-1]["status"] = '任务自行完成'
        

        # 3. 停止当前任务
        _stop_current_task()
        
        # 4. 启动目标任务
        _start_target_task(target_task, module_key, task_name)


    def _update_task_summary_ui(self):
        """更新任务汇总UI"""
        if not self.last_scheduled_task:
            return
        if not self.task_stats:
            self.last_scheduled_task.info_set("自动密函：历史记录", "暂无任务记录")
            return
            
        for stat in self.task_stats[::-1]:
            name = f"{stat['module_key']}，{stat['task_name']}，{stat['status']}"
            if stat['end_time']:
                time_range = f"{stat['start_time']}，{stat['end_time']}"
            else:
                time_range = f"{stat['start_time']}，--:--:--"
            self.last_scheduled_task.info_set(f"自动密函：历史记录{self.task_stats.index(stat)}", f"{name}，{time_range}")
        
    
    def _reset_ui_state(self):
        """重置UI状态"""
        try:
            timeout, time_start = 2 * 60 ,time.time()
            self._log_info(f"执行前置操作：重置UI状态 ({self.last_task_name}, 模块: {self.last_task_module}), 超时时间: {timeout}秒")
            # 不再历练页面，则执行循环
            while not self.find_lilian() and time.time() - time_start < timeout:
                self.send_key("esc")
                self.sleep(1)

                if self.in_team():
                    self._log_info("处理任务界面: 退出任务")
                    self.give_up_mission()
                
                if (letter_btn := self.find_letter_interface()):
                    self._log_info("处理密函耗尽：密函耗尽，点击确认后退出副本")
                    box = self.box_of_screen_scaled(
                        2560, 1440, 1190, 610, 2450, 820, 
                        name="letter_drag_area", hcenter=True
                    )
                    self.wait_until(
                        condition=lambda: not self.find_letter_interface(),
                        post_action=lambda: (
                            self.click_box_random(
                                letter_btn, use_safe_move=True,
                                safe_move_box=box, right_extend=0.1
                            ),
                            self.sleep(1),
                        ),
                        time_out=5,
                        raise_if_not_found=True,
                    )
                    self.give_up_mission()
                
                if (quit_btn := self.find_ingame_quit_btn()):
                    self._log_info("处理任务界面: 点击退出按钮")
                    self.click_box_random(quit_btn, right_extend=0.1, post_sleep=0, after_sleep=0.25)
                
                if self.find_letter_reward_btn():
                    self._log_info("处理任务界面: 选择密函奖励")
                    self.choose_letter_reward()   
                self.sleep(1)

            # 切换到相应任务
            if self.last_task_module == "default":
                self.sleep(1)
                self.switch_to_default_task()
                self.sleep(1)
                self.switch_to_task_level()
            else:
                self.switch_to_letter()
            
            self.sleep(0.3)
            self._log_info("UI状态重置完成")
        except Exception as e:
            self._log_info(f"UI状态重置可能未完全成功: {e}")
            raise e

    def switch_to_default_task(self):
        """切换到默认任务副本"""
        default_task_type = self.config.get("默认任务副本类型")
        if not default_task_type:
            self._log_info("未配置默认任务副本类型")
            return
        
        type_task, task_name = default_task_type.split(':')
        
        if type_task != "夜航手册":
            click_pos = (0.11, 0.16, 0.19, 0.18)
            # 委托搜索区域
            box_params = (2560, 1440, 2560*0.07, 1440*0.69, 2560*0.66, 1440*0.75)
            scroll_pos = (0.5, 0.4)
            scroll_amount = -600
            max_attempts = 10
        else:
            # 点击切换到夜航手册
            click_pos = (0.23, 0.16, 0.30, 0.18)
            # 夜航手册搜索区域
            box_params = (2560, 1440, 2560*0.07, 1440*0.22, 2560*0.12, 1440*0.84)
            scroll_pos = (0.1, 0.37)
            scroll_amount = -600
            max_attempts = 3
        
        timeout, now_time, clicked = 20, time.time(), False
        # 查找任务
        while not clicked and time.time() - now_time < timeout and self.is_enable_running():            
            # 双击，确保成功点击切换
            for _ in range(2):    
                # 点击切换到委托
                self.click_relative_random(*click_pos)
                self.sleep(0.02)
            self.sleep(1)
        
            # 确保滚动到初始位置
            for _ in range(2):  
                self.scroll_relative(*scroll_pos, scroll_amount)
                self.sleep(0.2)

            attempt = 0
            while attempt <= max_attempts and self.is_enable_running():
                attempt += 1
                self._log_info(f"尝试匹配任务: {task_name} (尝试{attempt}/{max_attempts})")
                match_box = self.wait_ocr(
                    box=self.box_of_screen_scaled(*box_params, name="weituo", hcenter=True),
                    match=re.compile(f'.*{task_name}.*'),
                    time_out=1,
                )
                if not match_box:
                    # 滚动
                    self.scroll_relative(0.5, 0.4, 600)
                else:
                    self.click_box_random(match_box[0])
                    clicked = True
                    break
            
        if not clicked:
            self._log_info(f"未找到任务: {task_name}")
            raise Exception(f"未找到任务: {task_name}")    

    def switch_to_task_level(self):
        """选择默认任务关卡等级"""
        
        if not (default_task_type := self.config.get("默认任务副本类型")):
            self._log_info("未配置默认任务副本类型")
            return
        
        type_task, task_name = default_task_type.split(':')
        
        # 夜航手册处理
        if type_task == "夜航手册":
            task_name = self.config.get("副本名称【夜航任务】")
            box_params = (2560 * 0.18, 1440 * 0.22, 2560 * 0.30, 1440 * 0.69)
        # 普通任务处理
        else:
            task_text = self.config.get("副本等级【普通任务】")
            task_name = task_text.split('.')[-1]
            box_params = (2560 * 0.10, 1440 * 0.19, 2560 * 0.17, 1440 * 0.62)
        
        clicked, attempt, now_time, timeout = False, 1, time.time(), 20
        # 统一的匹配逻辑
        while not clicked and time.time() - now_time < timeout and self.is_enable_running():
            self._log_info(f"尝试匹配: {task_name} (第{attempt}次)")
            match_box = self.ocr(
                box=self.box_of_screen_scaled(
                    2560, 1440, *box_params, name="等级", hcenter=True
                ),
                match=re.compile(f'.*{task_name}.*')
            )
            self._log_info(f"OCR匹配到的夜航副本或者任务等级: {match_box}")
            if match_box:
                self._log_info(f"匹配成功: {match_box}")
                if type_task == "夜航手册":
                    box = match_box[0]
                    y= box.y
                    to_y= y+box.height
                    self._log_info(f"夜航手册匹配到的框: {self.width*0.55}, {(y+0.1)}, {box.width}, {box.height}")
                    box = Box(self.width*0.55, y+(0.016*self.height), box.width, box.height)
                    self.draw_boxes(boxes=box)
                    for _ in range(2):
                        # 点击进入副本开始界面
                        self.click_box_random(box)
                        self.sleep(0.02)
                else:
                    self.click_box_random(match_box[0])
                clicked = True
            
            # 仅夜航手册在匹配失败后滚动
            if type_task == "夜航手册" and not clicked:
                self.scroll_relative(0.5, 0.4, 600)
                self.sleep(1)
            attempt += 1
        if not clicked:
            self._log_info(f"未找到匹配的{type_task}副本: {task_name}")
            raise Exception(f"未找到匹配的{type_task}副本: {task_name}")    

    def switch_to_letter(self):
        """选择密函任务"""
        self.click_relative_random(0.34, 0.15, 0.41, 0.18)
        self.sleep(1) 
        box_points = (2560 * 0.07, 1440 * 0.051, 2560 * 0.16, 1440 * 0.77)
        
        # 根据模块确定点击区域
        if self.last_task_module == '角色':
            box_points = (2560 * 0.07, 1440 * 0.051, 2560 * 0.16, 1440 * 0.77)
        elif self.last_task_module == '武器':
            box_points = (2560 * 0.28, 1440 * 0.051, 2560 * 0.38, 1440 * 0.77) 
        elif self.last_task_module == 'MOD':
            box_points = (2560 * 0.48, 1440 * 0.051, 2560 * 0.59, 1440 * 0.77) 
        else:
            raise Exception(f"进入密函任务：未知的模块: {self.last_task_module}")
        box = self.box_of_screen_scaled(
            2560, 1440, *box_points, name='密函任务类型', hcenter=True
        )
        clicked, flag = False, 0
        while not clicked and flag < 3 and self.is_enable_running():    
            text = self.wait_ocr(
                box=box,
                match=self.last_task_name,
                time_out=5,
                raise_if_not_found=True,
            )
            self.click_box_random(text[0])
            clicked = True
        if not clicked:
            self._log_info(f"进入密函任务：未找到匹配的{self.last_task_module}任务: {self.last_task_name}，无法点击进入")
            raise Exception(f"进入密函任务：未找到匹配的{self.last_task_module}任务: {self.last_task_name}，无法点击进入")       

    def get_letter_num(self):
        """获取当前密函数量，如果不在历练页面，直接返回100, 100, 100"""
  
        if not self.find_lilian():
            return 100, 100, 100
        # 切换到密函委托
        for _ in range(2):
            self.click_relative_random(0.34, 0.15, 0.41, 0.18)
            self.sleep(0.02) 

        self.sleep(1) 

        time_out, now_time = 3,time.time()
        rule_num, weapon_num, mod_num = None, None, None
        while (not isinstance(rule_num, (int, float)) or not isinstance(weapon_num, (int, float)) or not isinstance(mod_num, (int, float))) and time.time() - now_time < time_out and self.is_enable_running():

            rule_box_params = (2560, 1440, 2560*0.13, 1440*0.43, 2560*0.19, 1440*0.46)
            rule_box = self.box_of_screen_scaled(*rule_box_params, name="letter_num_rule", hcenter=True)
            rule_text = self.ocr(box=rule_box,match=re.compile(r'\d+'))
            if rule_text and not isinstance(rule_num, (int, float)):
                rule_num = int(re.sub(r'\D', '', rule_text[0].name))

            weapon_box_params = (2560, 1440, 2560*0.33, 1440*0.43, 2560*0.39, 1440*0.46)
            weapon_box = self.box_of_screen_scaled(*weapon_box_params, name="letter_num_weapon", hcenter=True)
            weapon_text = self.ocr(box=weapon_box,match=re.compile(r'\d+'))
            if weapon_text and not isinstance(weapon_num, (int, float)):
                weapon_num = int(re.sub(r'\D', '', weapon_text[0].name))

            mod_box_params = (2560, 1440, 2560*0.54, 1440*0.43, 2560*0.60, 1440*0.46)
            mod_box = self.box_of_screen_scaled(*mod_box_params, name="letter_num_mod", hcenter=True)
            mod_text = self.ocr(box=mod_box,match=re.compile(r'\d+'))
            if mod_text and not isinstance(mod_num, (int, float)):
                mod_num = int(re.sub(r'\D', '', mod_text[0].name))

        return rule_num, weapon_num, mod_num

    def find_lilian(self):
        """查找历练文本"""
        logger.debug("检查是否在历练页面")
        lilian, flag = None, 0
        box = self.box_of_screen_scaled(
            2560, 1440, 2560 * 0.05, 1440 * 0.001, 2560 * 0.09, 1440 * 0.05,
            name="lilian", hcenter=True
        )
        while not (lilian := self.ocr(box=box, match='历练')) and flag < 3 and self.is_enable_running():
            logger.debug(f"查找历练文本第{flag+1}次尝试")
            flag += 1
        return lilian