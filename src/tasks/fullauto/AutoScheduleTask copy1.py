import requests
from qfluentwidgets import FluentIcon
import time
import threading
import ctypes
from datetime import datetime

from ok import Logger, TaskDisabledException
from src.tasks.BaseDNATask import BaseDNATask
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.CommissionsTask import CommissionsTask
from src.tasks.BaseCombatTask import BaseCombatTask

# 导入具体的任务类
from src.tasks.fullauto.AutoExploration_Fast import AutoExploration_Fast
from src.tasks.AutoExpulsion import AutoExpulsion
# 占位：拆解任务尚未实现
# from src.tasks.AutoDismantle import AutoDismantle
from src.tasks.fullauto.Auto65ArtifactTask_Fast import Auto65ArtifactTask_Fast
from src.tasks.fullauto.Auto70jjbTask import Auto70jjbTask
from src.tasks.fullauto.AutoEscortTask import AutoEscortTask
from src.tasks.fullauto.AutoAllFishTask import AutoAllFishTask
from src.tasks.fullauto.ImportTask import ImportTask

logger = Logger.get_logger(__name__)

class AutoScheduleTask(DNAOneTimeTask, CommissionsTask, BaseCombatTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动密函委托"
        self.description = "整点自动检查密函任务并按照优先级匹配任务执行\n需在历练->委托页面启动"
        self.group_name = "全自动"
        self.group_icon = FluentIcon.CAFE
        self.last_check_hour = -1
        self.current_task_thread = None

        # 默认配置
        self.default_config = {
            # 默认任务配置
            "默认任务": "自动70级皎皎币本",
            # 模块优先级
            "委托": '角色>武器>MOD',
            # 任务优先级
            "关卡": '探险/无尽>驱离>拆解',
        }

        self.config_type = {
            "默认任务": {
                "type": "drop_down",
                "options": [
                    "自动70级皎皎币本",
                    "自动飞枪80护送（无需巧手）【需要游戏处于前台】",
                    "使用外部移动逻辑自动打本"
                ]
            }
        }

        self.config_description = {
            "默认任务": "当没有匹配的委托密函任务时，自动执行此任务",
            "委托": "使用 > 分隔优先级，越靠前优先级越高。\n例如：角色>武器>MOD",
            "关卡": "使用 > 分隔优先级，越靠前优先级越高。\n例如：探险/无尽>驱离>拆解\n仅支持探险/无尽、驱离、拆解",
        }

        # 任务映射关系
        self.TASK_MAPPING = {
            "探险/无尽": AutoExploration_Fast,
            "驱离": AutoExpulsion,
            # "拆解": AutoDismantle, # 尚未实现
        }

        # 匹配到的密函任务
        self.target_task = None
        
        # 默认任务映射
        self.DEFAULT_TASK_MAPPING = {
            "自动70级皎皎币本": Auto70jjbTask,
            "自动飞枪80护送（无需巧手）【需要游戏处于前台】": AutoEscortTask,
            "使用外部移动逻辑自动打本": ImportTask
        }
        
        self.retry_needed = False
        self.schedule_needed = False
        self.finished_tasks = set()
    
    def run(self):
        # 启动时立即执行一次检查
        logger.info("任务启动，立即执行一次调度检查")
        self.check_and_execute()
        
        # 如果当前刚好是整点，更新 last_check_hour 以避免重复触发
        now = datetime.now()
        if now.minute == 0:
            self.last_check_hour = now.hour

        while True:
            # 1. 检查时间：是否是整点，且当前小时未执行过
            now = datetime.now()
            # 允许在 0 分的 10 秒后触发，通过 last_check_hour 保证一小时只触发一次
            if now.minute == 0 and now.second >= 10 and now.hour != self.last_check_hour:
                logger.info(f"触发整点调度检查: {now}")
                self.last_check_hour = now.hour
                # self.finished_tasks.clear() # 新的一小时，清空已完成任务记录
                self.check_and_execute()
            
            # 2. 检查是否有异常重试请求
            if self.retry_needed:
                logger.warning("检测到任务异常结束，10秒后重新进行调度检查...")
                self.sleep(10)
                self.retry_needed = False
                self.check_and_execute()

            # 3. 检查是否有任务自然结束触发的调度请求  
            # ---------------- 暂时关闭 ----------------
            if self.schedule_needed:
                logger.info("检测到任务自然结束，立即进行调度检查...")
                self.schedule_needed = False
                self.check_and_execute()

            # 避免空转
            self.sleep(0.2)

    def on_stop(self):
        """
        当任务被手动停止时调用。
        """
        logger.info("AutoScheduleTask 被手动停止，正在停止子任务线程...")
        self._stop_current_thread()
        super().on_stop()
    
    def check_and_execute(self):
        API_URL = "https://wiki.ldmnq.com/v1/dna/instanceInfo"
        HEADERS = {"game-alias": "dna"}

        try:
            logger.info(f"开始请求API: {API_URL}")
            response = requests.get(API_URL, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # 处理返回的数据
            self.process_data(data)
            
        except Exception as e:
            logger.error(f"请求API失败或处理数据出错: {e}")
            # 出错时也尝试执行默认任务（如果需要的话，或者只打印日志）

    def process_data(self, data):
        if data.get("code") != 0:
            logger.error(f"API返回错误代码: {data.get('code')}")
            self.execute_default_task()
            return

        instance_info_list = data.get("data", [])
        logger.info(f"当前可选密函信息: {instance_info_list}")
        if not isinstance(instance_info_list, list):
             logger.error("API返回的data不是列表格式")
             self.execute_default_task()
             return
        
        # 1. 解析委托（模块）优先级配置
        commission_config = self.config.get("委托", "角色>武器>MOD")
        commission_order = [x.strip() for x in commission_config.split(">") if x.strip()]
        
        # 映射中文名称到API对应的key
        name_map = {
            "角色": "role", 
            "武器": "weapon", 
            "MOD": "mod"
        }
        
        # 转换成API key列表
        sorted_modules = []
        for name in commission_order:
            if name in name_map:
                sorted_modules.append(name_map[name])
        
        if not sorted_modules:
            logger.info("未配置有效的委托模块优先级，执行默认任务")
            self.execute_default_task()
            return

        # 2. 解析关卡（任务）优先级配置
        level_config = self.config.get("关卡", "探险/无尽>驱离>拆解")
        level_order = [x.strip() for x in level_config.split(">") if x.strip()]
        
        # 生成任务优先级映射 (名称 -> 索引，索引越小优先级越高)
        task_priority_map = {name: i for i, name in enumerate(level_order)}

        # 映射模块Key到列表索引 (API返回的数据列表顺序)
        module_index_map = {
            "role": 0,
            "weapon": 1,
            "mod": 2
        }

        tasks_to_execute = []

        # 3. 遍历排序后的模块
        for module_key in sorted_modules:
            index = module_index_map.get(module_key)
            # 检查索引是否越界
            if index is None or index >= len(instance_info_list):
                continue

            module_data_item = instance_info_list[index]
            module_instances = module_data_item.get("instances", [])
            
            if not module_instances:
                continue

            # 处理该模块下的所有任务
            current_module_tasks = []
            for task_info in module_instances:
                mapped_name = task_info.get("name") 
                if mapped_name and mapped_name in self.TASK_MAPPING:
                    # 获取优先级，如果在配置中找不到，则设为999（最低优先级）
                    priority = task_priority_map.get(mapped_name, 999)
                    
                    current_module_tasks.append({
                        "name": mapped_name,
                        "class": self.TASK_MAPPING[mapped_name],
                        "priority": priority,
                        "module_key": module_key,
                    })

            # 对当前模块的任务按任务优先级排序
            current_module_tasks.sort(key=lambda x: x["priority"])
            tasks_to_execute.extend(current_module_tasks)

        if tasks_to_execute:
            # 找到第一个要执行的任务 (优先级最高的模块中优先级最高的任务)
            # 且不在已完成列表中
            # ---------------- 暂时关闭 ----------------
            new_target_task = None
            for task in tasks_to_execute:
                if task['class'] not in self.finished_tasks:
                    new_target_task = task
                    break
            
            if not new_target_task:
                logger.info("所有匹配的任务均已完成，执行默认任务")
                self.execute_default_task()
                return

            # new_target_task = tasks_to_execute[0]

            # 检查是否需要切换任务
            if self.target_task and \
               self.target_task.get('name') == new_target_task['name'] and \
               self.target_task.get('module_key') == new_target_task['module_key']:
                if self.current_task_thread and self.current_task_thread.is_alive():
                    logger.info(f"任务 {new_target_task['name']} (Module: {new_target_task['module_key']}) 正在运行中，跳过切换")
                    return

            self.target_task = new_target_task
            logger.info(f"匹配到任务: {self.target_task['name']}，准备执行")
            
            # 立即执行任务 (会打断当前任务，如果有的话)
            self.execute_task(self.target_task["class"])
        else:
            logger.info("未匹配到任何有效任务，执行默认任务")
            self.execute_default_task()

    def execute_default_task(self):
        default_task_name = self.config.get("默认任务")
        
        if default_task_name and default_task_name in self.DEFAULT_TASK_MAPPING:
            task_class = self.DEFAULT_TASK_MAPPING[default_task_name]
            
            # 没有匹配的密函任务，清除设置的目标任务
            new_target_task = {
                'name': default_task_name, 
                'class': task_class, 
                'priority': -1,
                'module_key': 'default'
            }

            if self.target_task and \
               self.target_task.get('name') == new_target_task['name'] and \
               self.target_task.get('module_key') == new_target_task['module_key']:
                if self.current_task_thread and self.current_task_thread.is_alive():
                     logger.info(f"默认任务 {default_task_name} 正在运行中，跳过切换")
                     return

            self.target_task = new_target_task
            task_class = self.DEFAULT_TASK_MAPPING[default_task_name]
            logger.info(f"执行默认任务: {default_task_name}")
            self.execute_task(task_class)
        else:
            logger.warning(f"未找到默认任务配置或映射: {default_task_name}")

    def execute_task(self, task_class):
        # 实例化并执行任务
        # 使用独立的线程去执行，确保不阻塞主线程执行
        
        try:
            logger.info(f"准备切换到任务: {task_class.__name__}")

            # 1. 停止当前正在运行的任务线程（如果有）
            if self.current_task_thread and self.current_task_thread.is_alive():
                logger.info("检测到正在运行的任务线程，尝试停止...")
                self._stop_current_thread()
            
            # 2. 获取新任务实例
            # 使用 get_task_by_class 获取实例，确保依赖注入（如 global_config）
            next_task = self.get_task_by_class(task_class)
            
            # 创建停止事件
            stop_event = threading.Event()
            self.current_stop_event = stop_event
            
            # 注入停止逻辑，允许任务通过检查 stop_func 来响应停止信号
            original_stop_func = getattr(next_task, 'stop_func', lambda: False)
            next_task.stop_func = lambda: stop_event.is_set() or original_stop_func()
            
            # 定义线程运行函数
            def task_runner():
                try:
                    # 执行前置操作：重置页面状态
                    self.reset_ui_state(task_class.__name__)
                    
                    # 执行任务
                    logger.info(f"任务线程开始执行: {task_class.__name__}")
                    next_task.run()
                    
                    
                    # ---------------- 暂时关闭 ----------------
                    # 检查是否是自然结束（未被停止信号打断）
                    if not stop_event.is_set():
                        # 判断是否为默认任务
                        default_task_name = self.config.get("默认任务")
                        default_task_class = self.DEFAULT_TASK_MAPPING.get(default_task_name)
                        
                        if task_class != default_task_class:
                            logger.info(f"任务 {task_class.__name__} 自然结束，加入已完成列表")
                            self.finished_tasks.add(task_class)
                        else:
                            logger.info(f"默认任务 {task_class.__name__} 自然结束，不加入黑名单")
                            
                        self.schedule_needed = True
                        
                    self.info_set('当前任务',self.target_task['name'])
                except (TaskDisabledException, SystemExit):
                    logger.info(f"任务 {task_class.__name__} 已停止")
                except Exception as e:
                    logger.error(f"任务线程执行出错: {e}")
                    logger.info("任务异常终止，请求重新调度")
                    self.retry_needed = True
                finally:
                    logger.info(f"任务线程结束: {task_class.__name__}")

            # 3. 启动新线程
            self.current_task_thread = threading.Thread(target=task_runner, name=f"TaskThread-{task_class.__name__}")
            self.current_task_thread.daemon = True
            self.current_task_thread.start()
            logger.info(f"新任务线程已启动")
            
        except Exception as e:
            logger.error(f"启动任务失败: {e}")

    def _stop_current_thread(self):
        """尝试优雅停止当前线程，如果失败则强制终止"""
        # 1. 发送停止信号
        if hasattr(self, 'current_stop_event') and self.current_stop_event:
            logger.info("发送停止信号...")
            self.current_stop_event.set()
        
        # 2. 等待线程优雅退出 (最多等待5秒)
        self.current_task_thread.join(timeout=5)
        
        if not self.current_task_thread.is_alive():
            logger.info("旧任务线程已优雅停止")
            return

        # 3. 如果仍未停止，强制终止
        logger.warning("旧任务线程未响应停止信号，执行强制终止")
        self._terminate_thread(self.current_task_thread)
        self.current_task_thread.join(timeout=2)
        
        if self.current_task_thread.is_alive():
             logger.error("旧任务线程无法终止！")
        else:
             logger.info("旧任务线程已强制停止")

    def _terminate_thread(self, thread):
        """强行终止线程"""
        if not thread.is_alive():
            return

        exc = ctypes.py_object(SystemExit)
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(thread.ident), exc)
        if res == 0:
            logger.warning("非法的线程ID")
        elif res > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
            logger.error("PyThreadState_SetAsyncExc 失败")

    def reset_ui_state(self, task_name):
        """
        执行任务前的前置操作，重置页面到初始状态。
        """
        logger.info(f"执行前置操作：重置UI状态 ({task_name})")
        try:
            lilian = self.wait_ocr(
                box=self.box_of_screen_scaled(
                    2560, 1440, 2560 * 0.05, 1440 * 0.001, 2560 * 0.09, 1440 * 0.05,
                    name="lilian", hcenter=True
                ),
                match='历练',
                time_out=20,
            )
            logger.debug(f"当前是否处于历练页面: {lilian is not None}")
            if not lilian:
                # 如果密函耗尽了，会停在开始游戏界面，这时需要点击开始游戏回到队伍
                if (letter_btn:=self.find_letter_interface()):
                    box = self.box_of_screen_scaled(2560, 1440, 1190, 610, 2450, 820, name="letter_drag_area", hcenter=True)
                    self.wait_until(
                        condition=lambda: not self.find_letter_interface(),
                        post_action=lambda: (
                            self.click_box_random(letter_btn, use_safe_move=True, safe_move_box=box, right_extend=0.1),
                            self.sleep(1),
                        ),
                        time_out=5,
                        raise_if_not_found=True,
                    )
                # 处理退出任务，直到返回历练页面，超时时间39秒，30秒内出现队伍标识才会执行退出任务
                if self.wait_until(
                    post_action=self.give_up_mission,
                    condition=self.in_team, time_out=30, raise_if_not_found=True
                ):
                    # 先放弃当前任务
                    self.give_up_mission()
                    self.sleep(1.5)
                    self.send_key("esc")
                    self.wait_ocr(
                        box=self.box_of_screen_scaled(
                            2560, 1440, 2560 * 0.05, 1440 * 0.001, 2560 * 0.09, 1440 * 0.05,
                            name="lilian", hcenter=True
                        ),
                        match='历练',
                        time_out=20,
                        raise_if_not_found=True,
                    )
            # 切换到委托
            if task_name == "AutoEscortTask" or task_name == "Auto70jjbTask":
                self.click_relative_random(0.11, 0.16, 0.19, 0.18)
                self.sleep(1) 
           

            if task_name == "AutoEscortTask":
                self.click_relative_random(0.12, 0.15, 0.18, 0.18)
                self.scroll_relative(0.5, 0.5, 300)
                self.sleep(1)
                logger.debug(f"滚动后，点击进入")
                self.click_relative_random(0.12, 0.35, 0.21, 0.61)

            if task_name == "Auto70jjbTask":
                self.click_relative_random(0.12, 0.15, 0.18, 0.18)
                self.scroll_relative(0.5, 0.5, 300)
                self.sleep(1)
                logger.debug(f"滚动后，点击进入")
                self.click_relative_random(0.40, 0.34, 0.48, 0.56)   
                self.sleep(1) 
                self.click_relative_random(0.04, 0.37, 0.13, 0.39)   
                self.sleep(1) 

            # 密函本需要切换到密函页面
            if task_name == "AutoExploration_Fast" or task_name == "AutoExpulsion":     
                self.click_relative_random(0.34, 0.15, 0.41, 0.18)
                self.sleep(1) 

            if self.target_task["module_key"] in ['role','weapon','mod']:
                name = self.target_task["name"]
                box = None
                if self.target_task["module_key"] == 'role':
                    box = self.box_of_screen_scaled(
                        2560, 1440, 2560 * 0.07, 1440 * 0.051, 2560 * 0.16, 1440 * 0.77,
                        name='guan_qia', hcenter=True
                    )
                if self.target_task["module_key"] == 'weapon':
                    box = self.box_of_screen_scaled(
                        2560, 1440, 2560 * 0.28, 1440 * 0.051, 2560 * 0.38, 1440 * 0.77,
                        name='guan_qia', hcenter=True
                    )   
                if self.target_task["module_key"] == 'mod':
                    box = self.box_of_screen_scaled(
                        2560, 1440, 2560 * 0.48, 1440 * 0.051, 2560 * 0.59, 1440 * 0.77,
                        name='guan_qia', hcenter=True
                    )       
                text = self.wait_ocr(
                    box=box,
                    match=name,
                    time_out=5,
                    raise_if_not_found=True,
                )
                self.click_box_random(text[0])
                self.sleep(1)

            
            logger.info("UI状态重置完成")
        except Exception as e:
            logger.warning(f"UI状态重置可能未完全成功: {e}")


        
