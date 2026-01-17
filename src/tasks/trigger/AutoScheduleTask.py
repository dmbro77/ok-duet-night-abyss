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


class UiResetException(Exception):
    def __init__(self, message="UI重置异常"):
        self.message = message
        super().__init__(self.message)

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
            "token": "",
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
            "token":"接口请求密钥"
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
        self._log_info(f"调度任务已启动")
        # 使用 submit_periodic_task 提交任务，间隔 1 秒
        self.submit_periodic_task(1, self._scheduler_loop)

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
        # 主线程轮询留空，逻辑在独立线程里
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
    
    def _check_and_update_completed_task(self):
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
    
    def _should_trigger_hourly_check(self, now):
        """判断是否应该触发整点检查"""
        return (now.minute == 0 and now.second >= 10 and now.hour != self.last_check_hour)
    
    def _handle_scheduler_error(self, e):
        """处理调度器异常"""
        if self.task_stats and self.task_stats[-1]["end_time"] is None:
            self.task_stats[-1]["end_time"] = time.strftime("%H:%M:%S", time.localtime())
            self.task_stats[-1]["status"] = f'异常关闭: {e}'
        self._update_task_summary_ui()
    
    def _cleanup_on_exit(self):
        """退出时清理"""
        if self.task_stats and self.task_stats[-1]["end_time"] is None:
            self.task_stats[-1]["end_time"] = time.strftime("%H:%M:%S", time.localtime())
            self.task_stats[-1]["status"] = '手动关闭自动密函任务'
        self._update_task_summary_ui()

    def _scheduler_loop(self):
        """调度器主循环 - 每次执行一次迭代"""

        # 1. 检查是否启用
        if not self.is_enable_running():
            self._cleanup_on_exit()
            return False

        # 2. 验证配置
        if not self._validate_config():
            return False

        try:
            # 确保执行器处于运行状态 (唤醒执行器)，否则OCR会卡住
            if self.executor.paused:
                self.executor.start()
                
            now = datetime.now()
            
            # 3. 检查已完成的任务并更新状态
            should_check = self._check_and_update_completed_task()
            
            # 4. 整点检查
            if self._should_trigger_hourly_check(now):
                self._log_info(f"整点触发检查: {now.hour}:00")
                time.sleep(random.randint(5, 20))  # 随机延时5-20秒
                should_check = True
        
            # 5. 执行检查
            if should_check:
                task_class, module_key, task_name = self._calculate_target_task()
                self.last_check_hour = now.hour
                self.schedule_task(task_class, module_key, task_name)
                self._update_task_summary_ui()
                
            return True # 返回 True 继续下一次循环
            
        except Exception as e:
            self._log_info(f"调度器循环异常: {e}")
            self._handle_scheduler_error(e)
            time.sleep(10)  # 出错后等待10秒
            return True # 异常后继续尝试
 
    def _calculate_target_task(self):
        """计算得出最终可执行任务"""

        def _fetch_api_data(dev_code, token, max_retries=5):
            """获取API数据"""
            for retries in range(1, max_retries + 1):
                if not self.is_enable_running(): break
                try:
                    result = GameAPI(dev_code, token).default_role_for_tool()
                    if result.get('code') != 200:
                        self._log_info(f"API请求错误，60s后重试 ({retries}/{max_retries})...")
                    elif not isinstance(data := result.get('data', {}).get('instanceInfo'), list):
                        self._log_info(f"API返回数据异常，{60*retries}s后重试 ({retries}/{max_retries})...")
                    elif self.last_api_response_data == data:
                        self._log_info(f"API返回数据与上次相同，60s后重试 ({retries}/{max_retries})...")
                    else:
                        self._log_info(f"API返回数据: {data}")
                        if self.last_api_response_data: self._log_info("API数据已更新")
                        self.last_api_response_data = data
                        return True
                except Exception as e:
                    self._log_info(f"请求API失败 ({retries}): {e}")
                
                if retries < max_retries: time.sleep(60)
            return False

        def _get_sorted_tasks(instance_info):
            """获取排序后的任务列表"""
            # 解析配置
            mod_order = [x.strip() for x in self.config.get("密函委托优先级", "角色>武器>MOD").split(">") if x.strip()]
            mod_map = {"角色": 0, "武器": 1, "MOD": 2}
            valid_mods = [m for m in mod_order if m in mod_map]
            
            if not valid_mods:
                self._log_info("未配置有效的密函委托优先级")
                return []

            lvl_order = [x.strip() for x in self.config.get("关卡类型优先级", "探险/无尽>驱离>拆解").split(">") if x.strip()]
            lvl_map = {name: i for i, name in enumerate(lvl_order)}

            tasks = []
            for mod_key in valid_mods:
                idx = mod_map[mod_key]
                if idx >= len(instance_info): continue
                
                for task in instance_info[idx].get("instances", []):
                    name = task.get("name")
                    if name in self.TASK_MAPPING:
                        tasks.append({
                            "name": name,
                            "class": self.TASK_MAPPING[name],
                            "priority": lvl_map.get(name, 999),
                            "module_key": mod_key,
                            "module_priority": valid_mods.index(mod_key)
                        })

            return sorted(tasks, key=lambda x: (x["module_priority"], x["priority"]))

        def _get_default_task():
            name = self.config.get("默认任务")
            return (self.DEFAULT_TASK_MAPPING.get(name), "default", name) if name else (None, None, None)

        try:
            now_hour = datetime.now().hour
            self._log_info(f"请求API获取任务数据，小时信息：{self.last_check_hour}，{now_hour}")
            
            if not _fetch_api_data("", self.config.get("token"), 1 if self.last_check_hour == now_hour else 5):
                return _get_default_task()
            
            tasks = _get_sorted_tasks(self.last_api_response_data)
            self._log_info(f"api返回的可执行任务列表: {tasks}")
            self._log_info(f"已完成的任务列表: {self.finished_tasks}")
            # 查找首个可执行任务
            rule, weapon, mod = self.get_letter_num()
            logger.debug(f"当前密函数量 - 角色: {rule}, 武器: {weapon}, MOD: {mod}")
            
            letter_counts = {"角色": rule, "武器": weapon, "MOD": mod}
            
            for task in tasks:
                mod_key = task['module_key']
                if letter_counts.get(mod_key, 0) == 0:
                    self._log_info(f"{mod_key}任务 密函数量为0，跳过")
                    continue

                task_key = f"{mod_key}_{task['name']}_{task['class'].__name__}"
                if task_key not in self.finished_tasks:
                    self._log_info(f"匹配到任务: {task['name']} (模块: {mod_key})")
                    return task['class'], mod_key, task['name']

            self._log_info("未匹配到可执行的密函任务，执行默认任务")
            return _get_default_task()

        except Exception as e:
            self._log_info(f"请求API或处理数据失败: {e}")
            return _get_default_task()

    def schedule_task(self, task_class, module_key, task_name):
        """执行任务,如果当前有任务在运行,强制停止当前任务"""
        target_task = self.executor.get_task_by_class_name(task_class.__name__)
        if not target_task:
            self._log_info(f"未找到任务: {task_class.__name__}")
            return

        # 1. 检查是否需要切换任务
        self._log_info(f"任务变化信息: {self.last_task_module}->{module_key}, {self.last_task_name}->{task_name}, {self.last_scheduled_task}->{target_task}")
        
        if (self.last_task_module == module_key and 
            self.last_task_name == task_name and 
            isinstance(self.last_scheduled_task, target_task.__class__)):
            self._log_info(f"任务相同且正在运行，无需切换: {task_name}")
            return

        self.last_task_module, self.last_task_name = module_key, task_name

        # 2. 更新自行完成的任务状态
        if self.executor.current_task is None and self.task_stats:
            self.task_stats[-1].update({"end_time": time.strftime("%H:%M:%S", time.localtime()), "status": '任务自行完成'})

        # 3. 停止当前任务
        if current := self.executor.current_task:
            self._log_info(f"正在强制停止当前任务: {current.name}")
            self.executor.stop_current_task()
            
            start_time = time.time()
            while self.executor.current_task and time.time() - start_time < 60 and self.is_enable_running():
                time.sleep(1)
            
            if self.executor.current_task:
                raise Exception("当前任务停止超时")
            
            self.prev_task_is_force_stop = False
            if self.task_stats:
                self.task_stats[-1].update({"end_time": time.strftime("%H:%M:%S", time.localtime()), "status": '被调度停止'})
        else:
            self._log_info("当前没有正在运行的任务，不需要停止")

        # 4. 启动目标任务
        if not target_task.enabled or self.executor.current_task is None:
            # 重置UI (1次尝试 + 3次重试)
            for i in range(4):
                try:
                    self._reset_ui_state()
                    break
                except UiResetException as e:
                    if i == 3: raise UiResetException("UI重置失败3次")
                    self._log_info(f"UI重置异常: {e},等待10秒后重试3次")
                    self.sleep(10)

            self._log_info(f"正在启动任务: {module_key}-{task_name}")
            target_task.enable()
            self._log_info(f"任务 {task_name} 已启用，target_task.name=>{target_task.name}")
            self.go_to_tab(target_task.name)
            
            self.last_scheduled_task = target_task
            self.task_stats.append({
                "module_key": module_key, "task_name": task_name, "status": '运行中',
                "start_time": time.strftime("%H:%M:%S", time.localtime()), "end_time": None
            })
            if len(self.task_stats) > 50: self.task_stats.pop(0)
        else:
            self._log_info(f"任务 {task_name} 已经在运行中")
            self.last_scheduled_task = target_task


    def _update_task_summary_ui(self):
        """更新任务汇总UI"""
        if not self.last_scheduled_task: return
        if not self.task_stats:
            self.last_scheduled_task.info_set("自动密函：历史记录", "暂无任务记录")
            return
            
        for i, stat in enumerate(self.task_stats[::-1]):
            time_range = f"{stat['start_time']}，{stat['end_time'] or '--:--:--'}"
            self.last_scheduled_task.info_set(
                f"自动密函：历史记录{len(self.task_stats)-1-i}", 
                f"{stat['module_key']}，{stat['task_name']}，{stat['status']}，{time_range}"
            )
        
    
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
                    self.give_up_mission(timeout=60)
                
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
                    self.give_up_mission(timeout=60)
                
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
            raise UiResetException(f"UI重置异常: {e}")

    def switch_to_default_task(self):
        """切换到默认任务副本"""
        if not (default_task_type := self.config.get("默认任务副本类型")):
            self._log_info("未配置默认任务副本类型")
            return
        
        type_task, task_name = default_task_type.split(':')
        is_night = type_task == "夜航手册"
        
        if is_night:
            click_pos, box_params = (0.23, 0.16, 0.30, 0.18), (0.07, 0.22, 0.12, 0.84)
            scroll_pos, max_attempts = (0.1, 0.37), 3
        else:
            click_pos, box_params = (0.11, 0.16, 0.19, 0.18), (0.07, 0.69, 0.66, 0.75)
            scroll_pos, max_attempts = (0.5, 0.4), 10
            
        start_time = time.time()
        while time.time() - start_time < 20 and self.is_enable_running():
            # 双击切换，并确保滚动到初始位置
            for _ in range(2): 
                self.click_relative_random(*click_pos)
                self.sleep(0.02)
            self.sleep(1)
            
            for _ in range(2): 
                self.scroll_relative(*scroll_pos, -600)
                self.sleep(0.2)

            for attempt in range(1, max_attempts + 1):
                if not self.is_enable_running(): return
                self._log_info(f"尝试匹配任务: {task_name} (尝试{attempt}/{max_attempts})")
                
                box = self.box_of_screen_scaled(2560, 1440, 2560*box_params[0], 1440*box_params[1], 2560*box_params[2], 1440*box_params[3], name="weituo", hcenter=True)
                if match_box := self.wait_ocr(box=box, match=re.compile(f'.*{task_name}.*'), time_out=1):
                    self.click_box_random(match_box[0])
                    return
                
                self.scroll_relative(0.5, 0.4, 600)
            
        msg = f"未找到任务: {task_name}"
        self._log_info(msg)
        raise Exception(msg)    

    def switch_to_task_level(self):
        """选择默认任务关卡等级"""
        if not (default_task_type := self.config.get("默认任务副本类型")):
            self._log_info("未配置默认任务副本类型")
            return
        
        type_task, task_name = default_task_type.split(':')
        is_night = type_task == "夜航手册"
        
        if is_night:
            task_name = self.config.get("副本名称【夜航任务】")
            box_params = (0.18, 0.22, 0.30, 0.69)
        else:
            task_name = self.config.get("副本等级【普通任务】").split('.')[-1]
            box_params = (0.10, 0.19, 0.17, 0.62)
        
        attempt, flag, start_time = 1, 0, time.time()
        
        while time.time() - start_time < 20 and self.is_enable_running():
            self._log_info(f"尝试匹配: {task_name} (第{attempt}次)")
            box = self.box_of_screen_scaled(2560, 1440, 2560*box_params[0], 1440*box_params[1], 2560*box_params[2], 1440*box_params[3], name="等级", hcenter=True)
            
            if match_box := self.ocr(box=box, match=re.compile(f'.*{task_name}.*')):
                self._log_info(f"匹配成功: {match_box}")
                target_box = match_box[0]
                if is_night:
                    self._log_info(f"夜航手册匹配到的框: {self.width*0.55}, {(target_box.y+0.1)}, {target_box.width}, {target_box.height}")
                    target_box = Box(self.width*0.55, target_box.y+(0.016*self.height), target_box.width, target_box.height)
                    self.draw_boxes(boxes=target_box)
                    self.click_box_random(target_box)
                    self.sleep(0.02)
                
                self.click_box_random(target_box)
                return

            if is_night:
                flag += 1
                if flag > 2:
                    self.scroll_relative(0.5, 0.4, 600)
                    flag = 0
                self.sleep(1)
            attempt += 1

        msg = f"未找到匹配的{type_task}副本: {task_name}"
        self._log_info(msg)
        raise Exception(msg)    

    def switch_to_letter(self):
        """选择密函任务"""
        self.click_relative_random(0.34, 0.15, 0.41, 0.18)
        self.sleep(1) 
        
        module_points = { '角色': (0.07, 0.16), '武器': (0.28, 0.38), 'MOD': (0.48, 0.59) }
        
        if self.last_task_module not in module_points:
            raise Exception(f"进入密函任务：未知的模块: {self.last_task_module}")
            
        x1, x2 = module_points[self.last_task_module]
        box = self.box_of_screen_scaled(2560, 1440, 2560 * x1, 1440 * 0.051, 2560 * x2, 1440 * 0.77, name='密函任务类型', hcenter=True)
        
        for _ in range(3):
            if not self.is_enable_running(): break
            if text := self.wait_ocr(box=box, match=self.last_task_name, time_out=5, raise_if_not_found=True):
                self.click_box_random(text[0])
                return

        msg = f"进入密函任务：未找到匹配的{self.last_task_module}任务: {self.last_task_name}，无法点击进入"
        self._log_info(msg)
        raise Exception(msg) 

    def get_letter_num(self):
        """获取当前密函数量，如果不在历练页面，直接返回100, 100, 100"""
        if not self.find_lilian(): return 100, 100, 100
        
        # 切换到密函委托
        for _ in range(2):
            self.click_relative_random(0.34, 0.15, 0.41, 0.18)
            self.sleep(0.02)
        self.sleep(1)

        time_out, now_time = 3, time.time()
        nums = [None, None, None]  # rule, weapon, mod
        
        # 定义OCR区域参数
        configs = [
            (0.13, 0.19, "letter_num_rule"),   # rule
            (0.33, 0.39, "letter_num_weapon"), # weapon
            (0.54, 0.60, "letter_num_mod")     # mod
        ]

        while any(n is None for n in nums) and time.time() - now_time < time_out and self.is_enable_running():
            for i, (x1, x2, name) in enumerate(configs):
                if nums[i] is not None: continue
                
                box = self.box_of_screen_scaled(2560, 1440, 2560*x1, 1440*0.43, 2560*x2, 1440*0.46, name=name, hcenter=True)
                if text := self.ocr(box=box, match=re.compile(r'\d+')):
                    nums[i] = int(re.sub(r'\D', '', text[0].name))

        return tuple(nums)

    def find_lilian(self):
        """查找历练文本"""
        logger.debug("检查是否在历练页面")
        box = self.box_of_screen_scaled(2560, 1440, 2560 * 0.05, 1440 * 0.001, 2560 * 0.09, 1440 * 0.05, name="lilian", hcenter=True)
        for flag in range(3):
            if not self.is_enable_running(): break
            if lilian := self.ocr(box=box, match='历练'): return lilian
            logger.debug(f"查找历练文本第{flag+1}次尝试")
        return None


# import requests
import time
import random
import hashlib
import base64
import json
from urllib.parse import urlencode
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend


class DNABaseAPI:
    RSA_PUBLIC_KEY = (
        "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDGpdbezK+eknQZQzPOjp8mr/dP+QHwk8CRkQh6C6qFnfLH3tiyl0pnt3dePuFDnM1PUXGhCkQ157ePJCQgkDU2+mimDmXh0oLFn9zuWSp+U8uLSLX3t3PpJ8TmNCROfUDWvzdbnShqg7JfDmnrOJz49qd234W84nrfTHbzdqeigQIDAQAB"
    )
    BASE_URL = "https://dnabbs-api.yingxiong.com/"

    def __init__(self, dev_code, token=""):
        self.dev_code = dev_code
        self.token = token
        self.session = requests.Session()

    def _rsa_encrypt(self, text):
        try:
            pem_key = f"-----BEGIN PUBLIC KEY-----\n{self.RSA_PUBLIC_KEY}\n-----END PUBLIC KEY-----"
            public_key = serialization.load_pem_public_key(
                pem_key.encode('utf-8'),
                backend=default_backend()
            )
            encrypted = public_key.encrypt(
                text.encode('utf-8'),
                padding.PKCS1v15()
            )
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            raise Exception(f"[DNA] RSA Encryption failed: {str(e)}")

    def _rand_str(self, length=16):
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return "".join(random.choice(chars) for _ in range(length))

    def _md5_upper(self, text):
        return hashlib.md5(text.encode('utf-8')).hexdigest().upper()

    def _signature_hash(self, text):
        md5_hash = self._md5_upper(text)
        chars = list(md5_hash)
        positions = [1, 13, 5, 17, 7, 23]
        
        # Swap positions
        # TS: for (let i = 1; i < positions.length; i += 2)
        for i in range(1, len(positions), 2):
            p1 = positions[i-1]
            p2 = positions[i]
            if 0 <= p1 < len(chars) and 0 <= p2 < len(chars):
                chars[p1], chars[p2] = chars[p2], chars[p1]
        
        return "".join(chars)

    def _sign_fI(self, data, secret):
        # Sort keys
        sorted_keys = sorted(data.keys())
        pairs = []
        for k in sorted_keys:
            v = data[k]
            # TS: if (v !== null && v !== undefined && v !== "")
            if v is not None and v != "":
                pairs.append(f"{k}={v}")
        
        qs = "&".join(pairs)
        return self._signature_hash(f"{qs}&{secret}")

    def _xor_encode(self, text, key):
        tb = text.encode('utf-8')
        kb = key.encode('utf-8')
        out = []
        for i, b in enumerate(tb):
            # TS: (b & 255) + (kb[i % kb.length] & 255)
            # Python bytes are already ints 0-255
            k_byte = kb[i % len(kb)]
            e = b + k_byte
            out.append(f"@{e}")
        return "".join(out)

    def _build_signature(self, data, token=""):
        ts = int(time.time() * 1000)
        sign_data = data.copy()
        sign_data['timestamp'] = ts
        if token:
            sign_data['token'] = token
        elif 'token' in sign_data:
             # Ensure token is treated consistently if passed in data but we want to use empty string for signing if token arg is empty?
             # TS: build_signature(payload, tokenSig ? token : "")
             # If token is passed as argument, it overrides/sets 'token' in sign_data for calculation
             pass
        else:
             # If token not passed, set to empty?
             # TS: const sign_data = { ...data, timestamp: ts, token }
             # If token is undefined in TS call, it's undefined in object.
             # But here build_signature receives token from caller.
             sign_data['token'] = token

        sec = self._rand_str(16)
        sig = self._sign_fI(sign_data, sec)
        enc = self._xor_encode(sig, sec)
        
        return {'s': enc, 't': ts, 'k': sec}

    def _get_headers(self, payload, options=None):
        if options is None:
            options = {}
        
        token = options.get('token', self.token)
        tokenSig = options.get('tokenSig', False)
        dev_code = options.get('dev_code', self.dev_code)
        
        content_type = "application/x-www-form-urlencoded; charset=utf-8"
        headers = {
            "version": "1.1.3",
            "source": "ios",
            "Content-Type": content_type,
            "User-Agent": "DoubleHelix/4 CFNetwork/3860.100.1 Darwin/25.0.0"
        }
        
        if dev_code:
            headers['devCode'] = dev_code
        if token:
            headers['token'] = token
            
        if isinstance(payload, dict):
            # Sign the payload
            # TS: build_signature(payload, tokenSig ? token : "")
            sign_token = token if tokenSig else ""
            si = self._build_signature(payload, sign_token)
            
            payload['sign'] = si['s']
            payload['timestamp'] = si['t']
            
            # Encrypt key
            rk = si['k']
            ek = self._rsa_encrypt(rk)
            
            headers['rk'] = rk
            headers['key'] = ek
            
            # Convert payload to urlencoded string
            # TS: params.append(key, String(value))
            # We need to ensure values are strings
            payload_str_dict = {k: str(v) for k, v in payload.items()}
            payload_encoded = urlencode(payload_str_dict)
            
            return headers, payload_encoded
            
        return headers, payload

    def _dna_request(self, endpoint, data=None, options=None):
        if options is None:
            options = {}
            
        method = options.get('method', 'POST')
        sign = options.get('sign', False)
        token_sig = options.get('tokenSig', False)
        
        url = f"{self.BASE_URL}{endpoint}"
        
        if data is None:
            data = {}
            
        headers = {}
        request_body = data
        
        if sign:
            h, p = self._get_headers(
                payload=data, 
                options={'token': self.token, 'tokenSig': token_sig}
            )
            headers = h
            request_body = p
        else:
            # If not signing, just basic headers
            h, _ = self._get_headers(payload=None, options={'token': self.token})
            headers = h
            if isinstance(data, dict):
                request_body = urlencode(data)

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                data=request_body,
                timeout=10
            )
            
            # Handle response
            if "text/" in response.headers.get('Content-Type', ''):
                return {'code': -1, 'data': response.text}
            
            res_json = response.json()
            
            # TS: if (typeof raw_res.data === "string") { raw_res.data = JSON.parse(raw_res.data) }
            if isinstance(res_json.get('data'), str):
                try:
                    res_json['data'] = json.loads(res_json['data'])
                except:
                    pass
                    
            return res_json
            
        except Exception as e:
            print(f"Request failed: {str(e)}")
            return {'code': -1, 'msg': str(e)}

class GameAPI(DNABaseAPI):
    def default_role_for_tool(self, type_val=1, other_user_id=None):
        data = {'type': type_val}
        if other_user_id:
            data['otherUserId'] = other_user_id
            
        return self._dna_request(
            "role/defaultRoleForTool",
            data,
            {'sign': True, 'token': True, 'tokenSig': True}
        )
