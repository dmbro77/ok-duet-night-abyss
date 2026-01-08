import requests
from qfluentwidgets import FluentIcon
import time
import threading
import re
import queue
import ctypes
import win32api
import win32con
import random
from datetime import datetime

from ok import Logger, TaskDisabledException, og, Box, TriggerTask
from src.tasks.BaseDNATask import BaseDNATask
from src.tasks.CommissionsTask import CommissionsTask
from src.tasks.BaseCombatTask import BaseCombatTask

# 导入具体的任务类
from src.tasks.fullauto.AutoExploration_Fast import AutoExploration_Fast
from src.tasks.AutoExpulsion import AutoExpulsion
from src.tasks.fullauto.Auto65ArtifactTask_Fast import Auto65ArtifactTask_Fast
from src.tasks.fullauto.Auto70jjbTask import Auto70jjbTask
from src.tasks.fullauto.AutoEscortTask import AutoEscortTask
from src.tasks.fullauto.AutoEscortTask_Fast import AutoEscortTask_Fast
from src.tasks.fullauto.AutoAllFishTask import AutoAllFishTask
from src.tasks.fullauto.ImportTask import ImportTask

logger = Logger.get_logger(__name__+'====>')

class AutoScheduleTask(CommissionsTask, BaseCombatTask, TriggerTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动密函委托"
        self.description = "整点自动检查密函任务并按照优先级匹配任务执行\n需在历练->委托页面启动"
        self.group_name = "全自动"
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

        self.config_type = {
            "默认任务": {
                "type": "drop_down",
                "options": [
                    "自动70级皎皎币本",
                    "自动飞枪80护送（无需巧手）【需要游戏处于前台】",
                    "黎瑟：超级飞枪80护送",
                    "使用外部移动逻辑自动打本"
                ]
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
            "关卡类型优先级": "使用 > 分隔优先级，越靠前优先级越高，仅支持探险/无尽、驱离。\n例如：探险/无尽>驱离",
            "默认任务": "当没有匹配的委托密函任务时，自动执行此任务\n任务基于已有的任务执行，请对设置的任务做好相应配置",
            "默认任务副本类型": "可选普通任务和夜航任务\n根据选择的默认任务进行设置即可",
            "副本等级【普通任务】": "副本类型为正常委托时生效\n选择需要刷取的副本等级，根据选择的默认任务和副本类型进行设置",
            "副本名称【夜航任务】": "副本类型为夜航手册时生效\n填写需要刷取的夜航手册名称，根据选择的默认任务和副本类型进行设置\n列如：霜狱野蜂暗箭(不需要空格)",
        }

        # 任务映射关系
        self.TASK_MAPPING = {
            "探险/无尽": AutoExploration_Fast,
            "驱离": AutoExpulsion,
        }
        
        # 默认任务映射
        self.DEFAULT_TASK_MAPPING = {
            "自动70级皎皎币本": Auto70jjbTask,
            "自动飞枪80护送（无需巧手）【需要游戏处于前台】": AutoEscortTask,
            "黎瑟：超级飞枪80护送": AutoEscortTask_Fast,
            "使用外部移动逻辑自动打本": ImportTask
        }
        
        # 调度器核心状态
        self.init_param()

    
    @property
    def thread_pool_executor(self):
        return og.my_app.get_thread_pool_executor()


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
            logger.info(f"scroll_relative: pos={abs_pos}, input_delta={delta}, wheel_delta={target_wheel_delta}")

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
            logger.error(f"win32 scroll failed: {e}")
    
    def init_param(self):
        """初始化"""
          # 调度器核心状态
        self.last_task_name = None  # 最后任务名称
        self.last_task_module = None  # 最后任务模块
        self.last_scheduled_task = None  # 最后一个任务

        self.finished_tasks = set()  # 已完成的任务标识（仅密函任务）
        self.task_stats = []  # 任务统计信息
        
        self.last_check_hour = -1  # 上次检查的小时
        self.last_api_response_data = None # 上次 API 返回的数据

    @property
    def thread_pool_executor(self):
        return og.my_app.get_thread_pool_executor()

    def enable(self):
        if self.enabled:
            return
        super().enable()
        self.init_param()
        logger.info("调度任务已启动")
        self.thread_pool_executor.submit(self._scheduler_loop)

    def disable(self):
        super().disable()
        if self.last_scheduled_task:
            self.executor.stop_current_task()
        self.finished_tasks.clear()
        logger.info("调度任务已停止")

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
        """调度器主循环 - 仅负责检查并放入队列"""
        if not self._validate_config():
            return
        logger.info("调度器循环开始")
        # if self.executor.paused:
        #     self.executor.start()
        # self.info_set("自动密函：状态", "已启动")
        # return
   
        # true 启动时立即检查一次
        should_check = True
        while self.enabled and not self.executor.exit_event.is_set():
            try:
                # 确保执行器处于运行状态 (唤醒执行器)，否则OCR会卡住
                if self.executor.paused:
                    self.executor.start()
                now = datetime.now()
                # 1. 检查任务是否自己执行完成，执行完成，则添加到完成列表
                if self.last_scheduled_task:
                    # 如果任务被禁用了（说明执行完成了，或者被手动停止了）
                    if not self.last_scheduled_task.enabled:
                        logger.info(f"检测到任务 {self.last_scheduled_task.name} 已结束")
                        # 如果是密函任务，添加到已完成集合
                        if module_key != "default":
                            # 使用模块+任务名称+任务类名作为唯一标识
                            task_key = f"{module_key}_{task_name}_{self.last_scheduled_task.__class__.__name__}"
                            self.finished_tasks.add(task_key)
                            self.task_stats[-1]["end_time"] = time.strftime("%H:%M:%S", time.localtime())
                            self.task_stats[-1]["status"] = '已完成/被调度取消'
                            
                            logger.info(f"密函任务完成，加入已执行列表: {task_key}")
                        # 更新任务统计信息 
                        self._update_task_summary_ui()   
                        self.last_scheduled_task = None
                        should_check = True
                
                # 2. 整点检查（必须的）
                if now.minute == 0 and now.second >= 10 and now.hour != self.last_check_hour:
                    logger.info(f"整点触发检查: {now.hour}:00")
                    self.last_check_hour = now.hour
                    # 随机延时5-20秒，避免请求过于集中
                    time.sleep(random.randint(5, 20))
                    should_check = True
        
                # 3. 执行检查
                if should_check:
                    task_class,module_key,task_name = self._calculate_target_task()
                    self.schedule_task(task_class, module_key, task_name)
                    # 更新当前任务信息
                    self._update_task_ui(self.task_stats[-1])
                    should_check = False
                # 等待1秒后继续
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"调度器循环异常: {e}")
                time.sleep(10)  # 出错后等待10秒
                if self.task_stats[-1]["end_time"] == None:
                    self.task_stats[-1]["end_time"] = time.strftime("%H:%M:%S", time.localtime())
                    self.task_stats[-1]["status"] = '已完成/被调度取消'
                self._update_task_ui(self.task_stats[-1])
                self._update_task_summary_ui()   
        if self.task_stats[-1]["end_time"] == None:
            self.task_stats[-1]["end_time"] = time.strftime("%H:%M:%S", time.localtime())
            self.task_stats[-1]["status"] = '已完成/被调度取消'
        self._update_task_ui(self.task_stats[-1])
        self._update_task_summary_ui()   
        logger.info("调度线程循环结束")    
    


    def schedule_task(self, task_class, module_key, task_name):
        """执行任务,如果当前有任务在运行,强制停止当前任务"""
        target_task = self.executor.get_task_by_class_name(task_class.__name__)
        if not target_task:
            logger.error(f"未找到任务: {task_class.__name__}")
            return

        is_same_task = (
            self.last_task_module == module_key and
            self.last_task_name == task_name and
            isinstance(self.last_scheduled_task, task_class)
        )
            
        if is_same_task:
            logger.info(f"任务相同且正在运行，无需切换: {task_name}")
            return    

        self.last_task_module = module_key
        self.last_task_name = task_name
        current_task = self.executor.current_task
        
        # 如果当前有任务在运行，且不是目标任务
        if current_task and current_task != target_task:
            logger.info(f"正在强制停止当前任务: {current_task.name}")
            self.executor.stop_current_task() # 发送停止信号
            
            # 等待当前任务退出 (最多等60秒)
            for _ in range(60):
                if self.executor.current_task is None:
                    break
                time.sleep(1)
            raise Exception("当前任务停止超时")    

        if not target_task.enabled or current_task and current_task != target_task and self.executor.current_task is None:
            # 重置ui，回到历练页面
            self._reset_ui_state()
        # 启动目标任务
        if not target_task.enabled:
            logger.info(f"正在启动任务: {self.last_task_name}")
            target_task.enable()
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
            logger.info(f"任务 {self.last_task_name} 已经在运行中")
            # 记录当前调度的任务，用于后续追踪完成状态
            self.last_scheduled_task = target_task

        
 
    def _calculate_target_task(self):
        """计算目标任务"""
        API_URL = "https://wiki.ldmnq.com/v1/dna/instanceInfo"
        # API_URL = "http://localhost:8000/v1/dna/instanceInfo"
        HEADERS = {"game-alias": "dna"}
        
        try:
            logger.info("请求API获取任务数据")
            
            # 重试逻辑：最多请求20次，如果数据与上次相同则重试
            max_retries = 20
            current_data = None
            
            for i in range(max_retries):
                params = {"_t": int(time.time() * 1000)}
                try:
                    response = requests.get(API_URL, headers=HEADERS, params=params, timeout=10)
                    response.raise_for_status()
                    json_data = response.json()
                    
                    if json_data.get("code") != 0:
                        logger.error(f"API返回错误代码: {json_data.get('code')}")
                        if i == max_retries - 1: # 最后一次尝试失败
                            return self._get_default_task_info()
                        time.sleep(1*60)    
                        continue
                        
                    current_data = json_data.get("data", [])
                    if not isinstance(current_data, list):
                        logger.error("API返回的data不是列表格式")
                        if i == max_retries - 1:
                            return self._get_default_task_info()
                        time.sleep(1*60)
                        continue
                    
                    # 检查是否与上次数据相同
                    if self.last_api_response_data is not None and current_data == self.last_api_response_data:
                        logger.info(f"API返回数据与上次相同，正在重试 ({i+1}/{max_retries})...")
                        if i < max_retries - 1:
                            time.sleep(1*60)
                            continue
                    
                    # 数据不同或已达到最大重试次数，接受当前数据
                    if self.last_api_response_data is not None and current_data != self.last_api_response_data:
                        logger.info("API数据已更新")
                    
                    self.last_api_response_data = current_data
                    break
                    
                except Exception as req_err:
                    logger.warning(f"请求API失败 ({i+1}/{max_retries}): {req_err}")
                    if i < max_retries - 1:
                        time.sleep(1*60)
                    else:
                        return self._get_default_task_info()

            instance_info_list = self.last_api_response_data
            logger.info(f"API返回数据: {instance_info_list}")
            
            # 解析优先级配置
            commission_config = self.config.get("密函委托优先级", "角色>武器>MOD")
            commission_order = [x.strip() for x in commission_config.split(">") if x.strip()]
            
            module_index_map = {"角色": 0, "武器": 1, "MOD": 2}
            sorted_modules = [name for name in commission_order if name in module_index_map]
            
            if not sorted_modules:
                logger.info("未配置有效的密函委托优先级")
                return self._get_default_task_info()

            # 解析关卡优先级
            level_config = self.config.get("关卡类型优先级", "探险/无尽>驱离")
            level_order = [x.strip() for x in level_config.split(">") if x.strip()]
            task_priority_map = {name: i for i, name in enumerate(level_order)}

            tasks_to_execute = []

            # 遍历模块寻找任务
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
                        tasks_to_execute.append({
                            "name": mapped_name,
                            "class": self.TASK_MAPPING[mapped_name],
                            "priority": priority,
                            "module_key": module_key,
                        })

            # 按优先级排序
            tasks_to_execute.sort(key=lambda x: x["priority"])

            logger.info(f"api返回的可执行任务列表: {tasks_to_execute}")
            
            # 找到第一个未完成的任务
            for task in tasks_to_execute:
                # 使用模块+任务名称+任务类名作为唯一标识
                task_key = f"{task['module_key']}_{task['name']}_{task['class'].__name__}"
                # 默认有数量，可以执行
                rule_num, weapon_num, mod_num = 100,100,100
                if self.find_lilian():
                    rule_num, weapon_num, mod_num = self.get_letter_num()
                logger.info(f"当前密函数量 - 角色: {rule_num}, 武器: {weapon_num}, MOD: {mod_num}")
                if task_key not in self.finished_tasks:
                    if task['module_key'] == "角色" and rule_num == 0:
                        logger.info(f"角色任务 {task['name']} 密函数量为0，跳过")
                        continue
                    if task['module_key'] == "武器" and weapon_num == 0:
                        logger.info(f"武器任务 {task['name']} 密函数量为0，跳过")
                        continue
                    if task['module_key'] == "MOD" and mod_num == 0:
                        logger.info(f"MOD任务 {task['name']} 密函数量为0，跳过")
                        continue
                    logger.info(f"匹配到任务: {task['name']} (模块: {task['module_key']})")
                    return task['class'], task['module_key'], task['name']
            logger.info(f"已完成的任务: {self.finished_tasks}")
            logger.info("未匹配到可执行的密函任务，执行默认任务")
            return self._get_default_task_info()
            
        except Exception as e:
            logger.error(f"请求API或处理数据失败: {e}")
            return self._get_default_task_info()
    
    
    def _get_default_task_info(self):
        """获取默认任务信息"""
        default_task_name = self.config.get("默认任务")
        if default_task_name and default_task_name in self.DEFAULT_TASK_MAPPING:
            return self.DEFAULT_TASK_MAPPING[default_task_name], "default", default_task_name
        return None, None, default_task_name
    

    def _update_task_ui(self, current_stat):
        """更新任务UI"""
        module_key = current_stat["module_key"]
        task_name = current_stat["task_name"]
        status = current_stat["status"]
        start_time = current_stat["start_time"]
        end_time = current_stat["end_time"]
        logger.info(f"当前任务: {self.last_scheduled_task.info_set}")
        self.last_scheduled_task.info_set("自动密函：当前任务",f"{module_key}，{task_name}，{status}，{start_time}，{end_time if end_time else "--:--:--"}")

    
    def _update_task_summary_ui(self):
        """更新任务汇总UI"""
        if not self.task_stats:
            self.last_scheduled_task.info_set("自动密函：任务统计", "暂无任务记录")
            return
            
        summary_lines = []
        for stat in self.task_stats:
            name = f"{stat['module_key']}，{stat['task_name']}，{stat['status']}"
            if stat['end_time']:
                time_range = f"{stat['start_time']}，{stat['end_time']}"
            else:
                time_range = f"{stat['start_time']}，--:--:--"
            summary_lines.append(f"{name}，{time_range}")
        summary_text = "\n".join(summary_lines)
        self.last_scheduled_task.info_set("自动密函：任务统计", summary_text)
    
    def _reset_ui_state(self):
        """重置UI状态"""
        logger.info(f"执行前置操作：重置UI状态 ({self.last_task_name}, 模块: {self.last_task_module})")
        try:
            # 查找历练文本
            lilian = self.find_lilian()
            while not lilian:
                lilian = self.find_lilian()
                if lilian:
                    break
                self.send_key("esc")
                self.sleep(1)
                if self.in_team():
                    self.give_up_mission()
                if (letter_btn := self.find_letter_interface()):
                    logger.info("密函耗尽，点击确认后退出副本")
                    box = self.box_of_screen_scaled(2560, 1440, 1190, 610, 2450, 820, 
                                                   name="letter_drag_area", hcenter=True)
                    self.wait_until(
                        condition=lambda: not self.find_letter_interface(),
                        post_action=lambda: (
                            self.click_box_random(letter_btn, use_safe_move=True, 
                                                safe_move_box=box, right_extend=0.1),
                            self.sleep(1),
                        ),
                        time_out=5,
                        raise_if_not_found=True,
                    )
                    self.give_up_mission()
                if (quit_btn := self.find_ingame_quit_btn()):
                    self.click_box_random(quit_btn, right_extend=0.1, post_sleep=0, after_sleep=0.25)
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
            logger.info("UI状态重置完成")
        except Exception as e:
            logger.warning(f"UI状态重置可能未完全成功: {e}")
            raise e

    def switch_to_default_task(self):
        """切换到默认任务副本"""
        default_task_type = self.config.get("默认任务副本类型")
        if not default_task_type:
            logger.warning("未配置默认任务副本类型")
            return
        
        type_task, task_name = default_task_type.split(':')
        
        if type_task != "夜航手册":
            click_pos = (0.11, 0.16, 0.19, 0.18)
            # 委托搜索区域
            box_params = (2560, 1440, 2560*0.07, 1440*0.69, 2560*0.66, 1440*0.75)
            scroll_pos = (0.5, 0.4)
            scroll_amount = 600
            max_attempts = 10
        else:
            # 点击切换到夜航手册
            click_pos = (0.23, 0.16, 0.30, 0.18)
            # 夜航手册搜索区域
            box_params = (2560, 1440, 2560*0.07, 1440*0.22, 2560*0.12, 1440*0.84)
            scroll_pos = (0.1, 0.37)
            scroll_amount = int(self.height)
            max_attempts = 3
        
        timeout = 20
        now_time = time.time()
        # 查找任务
        clicked = False
        while not clicked and time.time() - now_time < timeout:            
            # 双击，确保成功点击切换
            for _ in range(2):    
                # 点击切换到委托
                self.click_relative_random(*click_pos)
                self.sleep(0.02)
            self.sleep(1)
        
            # 初始滚动
            self.scroll_relative(*scroll_pos, scroll_amount)
            self.sleep(1)
        
            for attempt in range(max_attempts):
                logger.info(f"尝试匹配任务: {task_name} (尝试{attempt+1}/{max_attempts})")
                
                match_box = self.ocr(
                    box=self.box_of_screen_scaled(*box_params, name="weituo", hcenter=True),
                    match=re.compile(f'.*{task_name}.*')
                )
                
                if match_box:
                    self.click_box_random(match_box[0])
                    clicked = True
                    break
                else:
                    # 滚动
                    self.scroll_relative(0.5, 0.4, 600)
                    self.sleep(1)
            
        if not clicked:
            logger.warning(f"未找到任务: {task_name}")
            raise Exception(f"未找到任务: {task_name}")    

    def switch_to_task_level(self):
        """选择默认任务关卡等级"""
        default_task_type = self.config.get("默认任务副本类型")
        if not default_task_type:
            logger.warning("未配置默认任务副本类型")
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
        
        timeout = 20
        now_time = time.time()
        clicked = False
        attempt = 1
        # 统一的匹配逻辑
        while not clicked and time.time() - now_time < timeout:
            logger.info(f"尝试匹配: {task_name} (第{attempt}次)")
            match_box = self.ocr(
                box=self.box_of_screen_scaled(
                    2560, 1440, *box_params, name="等级", hcenter=True
                ),
                match=re.compile(f'.*{task_name}.*')
                # match=re.compile(f'.*')
            )
            logger.info(f"OCR匹配到的夜航副本或者任务等级: {match_box}")
            if match_box:
                logger.info(f"匹配成功: {match_box}")
                if type_task == "夜航手册":
                    box = match_box[0]
                    y= box.y
                    to_y= y+box.height
                    logger.info(f"夜航手册匹配到的框: {self.width*0.55}, {(y+0.1)}, {box.width}, {box.height}")
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
            logger.warning(f"未找到匹配的{type_task}副本: {task_name}")
            raise Exception(f"未找到匹配的{type_task}副本: {task_name}")    

    def switch_to_letter(self):
        """选择密函"""
        self.click_relative_random(0.34, 0.15, 0.41, 0.18)
        self.sleep(1) 
        
        # 根据模块确定点击区域
        if self.last_task_module == '角色':
            box = self.box_of_screen_scaled(
                2560, 1440, 2560 * 0.07, 1440 * 0.051, 2560 * 0.16, 1440 * 0.77,
                name='guan_qia', hcenter=True
            )
        elif self.last_task_module == '武器':
            box = self.box_of_screen_scaled(
                2560, 1440, 2560 * 0.28, 1440 * 0.051, 2560 * 0.38, 1440 * 0.77,
                name='guan_qia', hcenter=True
            )   
        elif self.last_task_module == 'MOD':
            box = self.box_of_screen_scaled(
                2560, 1440, 2560 * 0.48, 1440 * 0.051, 2560 * 0.59, 1440 * 0.77,
                name='guan_qia', hcenter=True
            )
        else:
            logger.error(f"未知的模块: {self.last_task_module}")
            return
        
        clicked  = False
        flag = 0      
        while not clicked and flag < 3:    
            text = self.wait_ocr(
                box=box,
                match=self.last_task_name,
                time_out=5,
                raise_if_not_found=True,
            )
            self.click_box_random(text[0])
            clicked = True

    def get_letter_num(self):
        """获取当前密函数量"""

        # 切换到密函委托
        for _ in range(2):
            self.click_relative_random(0.34, 0.15, 0.41, 0.18)
            self.sleep(0.02) 

        self.sleep(1) 

        time_out = 5
        now_time = time.time()
        rule_num, weapon_num, mod_num = None, None, None
        while (not isinstance(rule_num, (int, float)) or not isinstance(weapon_num, (int, float)) or not isinstance(mod_num, (int, float))) and time.time() - now_time < time_out:

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

            mod_box_params = (2560, 1440, 2560*0.54, 1440*0.43, 2560*0.59, 1440*0.46)
            mod_box = self.box_of_screen_scaled(*mod_box_params, name="letter_num_mod", hcenter=True)
            mod_text = self.ocr(box=mod_box,match=re.compile(r'\d+'))
            if mod_text and not isinstance(mod_num, (int, float)):
                mod_num = int(re.sub(r'\D', '', mod_text[0].name))

        return rule_num, weapon_num, mod_num
    

    def find_lilian(self):
        """查找历练文本"""
        lilian = None
        flag = 0
        logger.debug("查找历练文本")
        while not lilian and flag < 3:
            logger.debug(f"查找历练文本第{flag+1}次尝试")
            lilian = self.ocr(
                box=self.box_of_screen_scaled(
                    2560, 1440, 2560 * 0.05, 1440 * 0.001, 2560 * 0.09, 1440 * 0.05,
                    name="lilian", hcenter=True
                ),
                match='历练',
            )
            if lilian:
                break
            flag += 1
        return lilian