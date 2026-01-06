import requests
from qfluentwidgets import FluentIcon
import time
import threading
import re
import ctypes
import win32api
import win32con
import random
from datetime import datetime

from ok import Logger, TaskDisabledException, og
from src.tasks.BaseDNATask import BaseDNATask
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
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

class AutoScheduleTask(DNAOneTimeTask, CommissionsTask, BaseCombatTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动密函委托"
        self.description = "整点自动检查密函任务并按照优先级匹配任务执行\n需在历练->委托页面启动"
        self.group_name = "全自动"
        self.group_icon = FluentIcon.CAFE
        
        # 默认配置（仅保留业务配置）
        self.default_config = {
            # 默认任务配置
            "默认任务": "自动70级皎皎币本",
            "默认任务副本类型": "角色技能材料:扼守/无尽",
            "默认任务副本等级": "70",
            # 模块优先级
            "密函委托优先级": '角色>武器>MOD',
            # 任务优先级
            "关卡类型优先级": '探险/无尽>驱离',
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
                    "委托:铜币:勘察无尽",
                    "委托:角色经验:避险",
                    "委托:武器经验:驱逐",
                    "委托:角色突破材料:探险/无尽",
                    "委托:武器突破材料:调停",
                    "委托:魔之楔:驱离",
                    "委托:深红凝珠:护送",
                    "委托:角色技能材料:追缉",
                    "委托:角色技能材料:扼守/无尽",
                    "委托:铸造材料:迁移",
                    "夜航手册:lv.20",
                    "夜航手册:lv.30",
                    "夜航手册:lv.40",
                    "夜航手册:lv.50",
                    "夜航手册:lv.55",
                    "夜航手册:lv.60",
                    "夜航手册:lv.65",
                    "夜航手册:lv.70",
                    "夜航手册:lv.80"
                ]
            },
            "默认任务副本等级或者夜航选项": {
                "type": "drop_down",
                 "options": [
                    "委托:lv.5", "委托:lv.10", "委托:lv.15", "委托:lv.20", "委托:lv.30", "委托:lv.35", "委托:lv.40", "委托:lv.50", "委托:lv.60", "委托:lv.70", "委托:lv.80", "委托:lv.100",
                ]
            },
        }

        self.config_description = {
            "默认任务": "当没有匹配的委托密函任务时，自动执行此任务\n任务基于已有的任务执行，请对设置的默认任务做好相应配置",
            "默认任务副本类型": "选择要执行的任务类型，根据选择的默认任务进行设置",
            "默认任务副本等级": "选择需要刷取的副本等级，根据选择的默认任务和副本类型进行设置",
            "密函委托优先级": "使用 > 分隔优先级，越靠前优先级越高，只能填写角色、武器、MOD。\n例如：角色>武器>MOD",
            "关卡类型优先级": "使用 > 分隔优先级，越靠前优先级越高，仅支持探险/无尽、驱离。\n例如：探险/无尽>驱离",
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
        self.current_sub_task = None  # 当前正在运行的任务实例
        self.current_task_name = None  # 当前任务名称
        self.current_task_module = None  # 当前任务模块
        
        self.scheduler_thread = None  # 调度器监控线程
        self.task_thread = None  # 任务执行线程
        
        self.scheduler_lock = threading.Lock()  # 调度器锁
        self.task_stop_event = threading.Event()  # 任务停止事件
        self.scheduler_running = True  # 调度器运行标志
        self.scheduler_paused = False  # 调度器暂停标志（不修改父类的_paused）
        
        self.finished_tasks = set()  # 已完成的任务标识（仅密函任务）
        self.task_stats = []  # 任务统计信息
        
        self.last_check_hour = -1  # 上次检查的小时
        self.force_check = False  # 强制检查标志
    
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
    
    def run(self):
        """调度器主入口 - 简化版本"""
        # 验证配置
        if not self._validate_config():
            return
        
        logger.info("自动密函调度器启动")
        self.info_set("自动密函：调度状态", "运行中")
        
        try:
            # 启动调度器监控线程
            self.scheduler_running = True
            self.scheduler_paused = False
            self.scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                name="AutoScheduleScheduler"
            )
            self.scheduler_thread.daemon = True
            self.scheduler_thread.start()
            
            logger.info("调度器监控线程已启动，等待整点或任务结束触发检查...")
            
            # 主线程等待调度器结束
            while self.enabled and self.scheduler_running:
                self.sleep(1)
                
        except TaskDisabledException:
            logger.info("调度器被手动停止")
        except Exception as e:
            logger.error('调度器主循环异常', e)
            raise
        finally:
            self._cleanup()
            logger.info("调度器已完全停止")
    
    def _validate_config(self):
        """验证必需配置"""
        required_configs = [
            "默认任务副本类型",
            "默认任务副本等级", 
            "默认任务",
            "密函委托优先级",
            "关卡类型优先级"
        ]
        
        for config_key in required_configs:
            if not self.config.get(config_key):
                self.info_set(f"自动密函：{config_key}", "未配置")
                logger.error(f"配置缺失: {config_key}")
                return False
        
        return True
    
    def _scheduler_loop(self):
        """调度器主循环 - 简化版本"""
        logger.info("调度器循环开始")
        
        # 启动时立即检查一次
        self._check_and_switch_task()
        
        while self.enabled and self.scheduler_running:
            try:
                # 检查调度器是否暂停
                if self.scheduler_paused:
                    logger.debug("调度器暂停中，等待恢复...")
                    self.sleep(1)
                    continue
                    
                now = datetime.now()
                should_check = False
                
                # 1. 整点检查（必须的）
                if now.minute == 0 and now.second >= 10 and now.hour != self.last_check_hour:
                    logger.info(f"整点触发检查: {now.hour}:00")
                    self.last_check_hour = now.hour
                    # 随机延时5-20秒，避免请求过于集中
                    self.sleep(random.randint(5, 20))
                    should_check = True
                
                # 2. 强制检查（任务结束触发）
                if self.force_check:
                    logger.info("强制检查触发（任务结束）")
                    should_check = True
                    self.force_check = False
                
                # 3. 执行检查
                if should_check:
                    self._check_and_switch_task()
                
                # 等待1秒后继续
                self.sleep(1)
                
            except Exception as e:
                logger.error(f"调度器循环异常: {e}")
                self.sleep(5)  # 出错后等待5秒
    
    def _check_and_switch_task(self):
        """检查并切换任务 - 核心逻辑"""
        try:
            # 检查调度器是否暂停
            if self.scheduler_paused:
                logger.debug("调度器暂停中，跳过任务检查")
                return
            
            # 1. 获取新的目标任务
            task_class, module_key, task_name = self._calculate_target_task()
            
            if not task_class:
                logger.info("未找到可执行的任务")
                return
            
            with self.scheduler_lock:
                # 再次检查暂停状态（因为可能在获取任务过程中被暂停）
                if self.scheduler_paused:
                    logger.debug("调度器已被暂停，取消任务切换")
                    return
                
                # 2. 检查是否与当前任务相同
                is_same_task = (
                    self.current_sub_task and 
                    isinstance(self.current_sub_task, task_class) and
                    self.current_task_module == module_key and
                    self.current_task_name == task_name
                )
                
                if is_same_task:
                    logger.info(f"任务相同且正在运行，无需切换: {task_name}")
                    return
                
                # 3. 停止当前任务（必须停止，因为任务不同）
                if self.current_sub_task:
                    logger.info(f"停止当前任务以执行新任务: {task_name}")
                    self._stop_current_task_immediately()
                
                # 4. 启动新任务
                logger.info(f"启动新任务: {task_name} (模块: {module_key})")
                self._start_new_task(task_class, module_key, task_name)
                
        except Exception as e:
            logger.error(f"检查并切换任务失败: {e}")
    
    def _calculate_target_task(self):
        """计算目标任务"""
        API_URL = "https://wiki.ldmnq.com/v1/dna/instanceInfo"
        HEADERS = {"game-alias": "dna"}
        
        try:
            logger.info("请求API获取任务数据")
            params = {"_t": int(time.time() * 1000)}
            response = requests.get(API_URL, headers=HEADERS, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                logger.error(f"API返回错误代码: {data.get('code')}")
                return self._get_default_task_info()

            instance_info_list = data.get("data", [])
            if not isinstance(instance_info_list, list):
                logger.error("API返回的data不是列表格式")
                return self._get_default_task_info()
            
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
            
            # 找到第一个未完成的任务
            for task in tasks_to_execute:
                # 使用模块+任务名称+任务类名作为唯一标识
                task_key = f"{task['module_key']}_{task['name']}_{task['class'].__name__}"
                if task_key not in self.finished_tasks:
                    logger.info(f"匹配到任务: {task['name']} (模块: {task['module_key']})")
                    return task['class'], task['module_key'], task['name']
            
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
    
    def _stop_current_task_immediately(self):
        """立即停止当前任务（强制停止）"""
        if not self.current_sub_task:
            return
        
        task_info = f"{self.current_task_name} (模块: {self.current_task_module})"
        logger.info(f"立即停止当前任务: {task_info}")
        
        try:
            # 设置停止事件
            self.task_stop_event.set()
            
            # 强制停止任务
            self.current_sub_task.disable()
            
            # 尝试调用任务的停止方法（如果有）
            if hasattr(self.current_sub_task, 'stop_task'):
                self.current_sub_task.stop_task()
            
            # 等待一小段时间确保任务感知到停止
            self.sleep(0.5)
            
            logger.info(f"任务已强制停止: {task_info}")
            
        except Exception as e:
            logger.error(f"停止任务时出错: {task_info}", e)
        finally:
            # 清理状态
            self.current_sub_task = None
            self.current_task_name = None
            self.current_task_module = None
            self.task_stop_event.clear()
    
    def _start_new_task(self, task_class, module_key, task_name):
        """启动新任务"""
        try:
            # 获取任务实例
            task = self.get_task_by_class(task_class)
            
            if task is self:
                logger.error(f"严重错误: get_task_by_class 返回了自身，跳过任务")
                return
            
            # 更新状态
            self.current_sub_task = task
            self.current_task_name = task_name
            self.current_task_module = module_key
            
            # 记录统计
            start_time = datetime.now().strftime("%H:%M:%S")
            current_stat = {
                "task": task_name,
                "module": module_key,
                "start_time": start_time,
                "end_time": "",
                "status": "执行中"
            }
            self.task_stats.append(current_stat)
            
            # 更新UI
            self._update_task_ui("执行中", start_time, task_name, module_key)
            
            # 启动任务执行线程
            self.task_stop_event.clear()
            self.task_thread = threading.Thread(
                target=self._execute_task,
                args=(task, task_name, module_key, current_stat),
                name=f"Task-{task_name}"
            )
            self.task_thread.daemon = True
            self.task_thread.start()
            
            logger.info(f"任务已启动: {task_name} (模块: {module_key}, 类型: {task_class.__name__})")
            
        except Exception as e:
            logger.error(f"启动任务失败: {task_name} (模块: {module_key})", e)
            self.current_sub_task = None
            self.current_task_name = None
            self.current_task_module = None
    
    def _execute_task(self, task, task_name, module_key, current_stat):
        """执行任务"""
        try:
            # 保存原始info_set并替换
            original_info_set = task.info_set
            task.info_set = self.info_set
            
            # 执行前置操作
            self._reset_ui_state(task_name, module_key)
            
            logger.info(f"开始执行任务: {task_name}")
            
            # 执行任务
            task.run()
            
            # 任务自然完成（没有被disable打断）
            current_stat["status"] = "已完成"
            logger.info(f"任务自然完成: {task_name}")
            
            # 如果是密函任务，添加到已完成集合
            if module_key != "default":
                # 使用模块+任务名称+任务类名作为唯一标识
                task_key = f"{module_key}_{task_name}_{task.__class__.__name__}"
                self.finished_tasks.add(task_key)
                logger.info(f"密函任务完成，加入已执行列表: {task_key}")
            
            # 标记需要强制检查
            self.force_check = True
            
        except TaskDisabledException:
            # 任务被调度器打断
            current_stat["status"] = "被中断"
            logger.info(f"任务被调度器中断: {task_name}")
        except Exception as e:
            # 任务执行出错
            current_stat["status"] = "出错"
            logger.error(f"任务执行出错: {task_name}", e)
            self.force_check = True  # 出错也触发检查
        finally:
            # 更新统计和UI
            end_time = datetime.now().strftime("%H:%M:%S")
            current_stat["end_time"] = end_time
            
            # 更新UI
            self._update_task_ui(current_stat["status"], end_time, task_name, module_key)
            self._update_task_summary_ui()
            
            # 恢复原始info_set
            if 'original_info_set' in locals():
                task.info_set = original_info_set
            
            # 清理状态（如果不是被调度器停止的）
            with self.scheduler_lock:
                if self.current_sub_task == task:
                    self.current_sub_task = None
                    self.current_task_name = None
                    self.current_task_module = None
                    self.task_stop_event.clear()
    
    def _update_task_ui(self, status, time_str, task_name, module_key):
        """更新任务UI"""
        self.info_set("自动密函：当前任务", task_name)
        self.info_set("自动密函：任务模块", module_key)
        self.info_set("自动密函：任务状态", status)
        
        if ":" in time_str:  # 判断是否为时间格式
            if status == "执行中":
                self.info_set("自动密函：开始时间", time_str)
            else:
                self.info_set("自动密函：结束时间", time_str)
    
    def _update_task_summary_ui(self):
        """更新任务汇总UI"""
        if not self.task_stats:
            self.info_set("自动密函：任务总计", "暂无任务记录")
            return
            
        task_groups = {}
        for stat in self.task_stats:
            name = f"{stat['task']}({stat['module']})"
            if name not in task_groups:
                task_groups[name] = []
            
            if stat['end_time']:
                time_range = f"{stat['start_time']}-{stat['end_time']}"
            else:
                time_range = f"{stat['start_time']}-进行中"
            task_groups[name].append(time_range)
        
        summary_lines = []
        for name, ranges in task_groups.items():
            ranges_str = "，".join(ranges)
            summary_lines.append(f"{name}，{ranges_str}")
            
        summary_text = "\n".join(summary_lines)
        self.info_set("自动密函：任务总计", summary_text)
    
    def _reset_ui_state(self, task_name, module_key):
        """重置UI状态"""
        logger.info(f"执行前置操作：重置UI状态 ({task_name}, 模块: {module_key})")
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
            if module_key == "default":
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
    
    def _cleanup(self):
        """清理资源"""
        logger.info("清理调度器资源")
        self.scheduler_running = False
        
        # 停止当前任务
        if self.current_sub_task:
            self._stop_current_task_immediately()
        
        # 等待调度器线程结束
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=3)
        
        # 等待任务线程结束
        if self.task_thread and self.task_thread.is_alive():
            self.task_thread.join(timeout=3)
    
    # ================ 暂停/恢复相关方法 ================
    
    def pause(self):
        """暂停调度器和当前任务"""
        logger.info("暂停调度器和当前任务")
        
        # 1. 设置调度器暂停标志
        self.scheduler_paused = True
        self.info_set("自动密函：调度状态", "已暂停")
        
        # 2. 暂停当前运行的任务
        if self.current_sub_task:
            try:
                logger.info(f"暂停当前任务: {self.current_task_name}")
                
                # 调用子任务的暂停方法（如果子任务支持）
                if hasattr(self.current_sub_task, 'pause'):
                    self.current_sub_task.pause()
                else:
                    # 如果子任务没有pause方法，设置其_paused标志
                    self.current_sub_task._paused = True
                
                # 更新UI
                self.info_set("自动密函：任务状态", "已暂停")
                
            except Exception as e:
                logger.error(f"暂停子任务失败: {e}")
    
    def unpause(self):
        """恢复调度器和任务运行"""
        logger.info("恢复调度器和任务运行")
        
        # 1. 清除暂停标志
        self.scheduler_paused = False
        self.info_set("自动密函：调度状态", "运行中")
        
        # 2. 恢复当前任务
        if self.current_sub_task:
            try:
                logger.info(f"恢复当前任务: {self.current_task_name}")
                
                # 调用子任务的恢复方法（如果子任务支持）
                if hasattr(self.current_sub_task, 'unpause'):
                    self.current_sub_task.unpause()
                else:
                    # 如果子任务没有unpause方法，清除其_paused标志
                    self.current_sub_task._paused = False
                
                # 更新任务状态
                self.info_set("自动密函：任务状态", "执行中")
                
            except Exception as e:
                logger.error(f"恢复子任务失败: {e}")
        
        # 3. 强制触发一次检查
        self.force_check = True
 
    # ================ 原有的辅助方法 ================
    
    def switch_to_default_task(self):
        """切换到默认任务副本"""
        default_task_type = self.config.get("默认任务副本类型")
        # 点击切换到委托
        self.click_relative_random(0.11, 0.16, 0.19, 0.18)
        self.sleep(1) 
        clicked  = False
        flag = 0
        self.scroll_relative(0.5, 0.4, int(self.width))
        self.sleep(1)
        while not clicked and flag < 10:
            logger.info(f"滚动副本: 600")
            self.scroll_relative(0.5, 0.4, 600)
            self.sleep(1)
            logger.info(f"尝试匹配默认任务副本类型: {default_task_type.split(':')[2]}")
            match_box = self.ocr(
                box=self.box_of_screen_scaled(
                    2560, 1440, 2560 * 0.07, 1440 * 0.69, 2560 * 0.66, 1440 * 0.75,
                    name="weituo", hcenter=True
                ),
                match=re.compile(f'.*{default_task_type.split(":")[2]}.*') 
            )
            logger.info(f"匹配到的默认任务副本类型: {match_box}")
            if match_box:
                self.click_box_random(match_box[0])
                clicked = True
                break
            else:
                flag += 1
    
    def switch_to_task_level(self):
        """选择默认任务关卡等级"""
        clicked  = False
        flag = 0
        default_task_level = self.config.get("默认任务副本等级")
        while not clicked and flag < 3:
            logger.info(f"尝试匹配默认任务副本等级: {default_task_level}")
            match_box = self.ocr(
                box=self.box_of_screen_scaled(
                    2560, 1440, 2560 * 0.10, 1440 * 0.19, 2560 * 0.17, 1440 * 0.62,
                    name="等级", hcenter=True
                ),
                match=re.compile(f'.*{default_task_level}.*')
            )
            logger.info(f"匹配到的默认任务副本等级: {match_box}")
            if match_box:
                self.click_box_random(match_box[0])
                clicked = True
                break
            else:
                flag += 1
    
    def switch_to_letter(self):
        """选择密函"""
        self.click_relative_random(0.34, 0.15, 0.41, 0.18)
        self.sleep(1) 
        
        # 根据模块确定点击区域
        if self.current_task_module == '角色':
            box = self.box_of_screen_scaled(
                2560, 1440, 2560 * 0.07, 1440 * 0.051, 2560 * 0.16, 1440 * 0.77,
                name='guan_qia', hcenter=True
            )
        elif self.current_task_module == '武器':
            box = self.box_of_screen_scaled(
                2560, 1440, 2560 * 0.28, 1440 * 0.051, 2560 * 0.38, 1440 * 0.77,
                name='guan_qia', hcenter=True
            )   
        elif self.current_task_module == 'MOD':
            box = self.box_of_screen_scaled(
                2560, 1440, 2560 * 0.48, 1440 * 0.051, 2560 * 0.59, 1440 * 0.77,
                name='guan_qia', hcenter=True
            )
        else:
            logger.error(f"未知的模块: {self.current_task_module}")
            return
        
        clicked  = False
        flag = 0      
        while not clicked and flag < 3:    
            text = self.wait_ocr(
                box=box,
                match=self.current_task_name,
                time_out=5,
                raise_if_not_found=True,
            )
            self.click_box_random(text[0])
            clicked = True
    
    def find_lilian(self):
        """查找历练文本"""
        lilian = None
        flag = 0
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