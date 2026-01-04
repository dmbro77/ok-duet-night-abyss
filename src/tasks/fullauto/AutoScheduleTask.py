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
from src.tasks.fullauto.AutoEscortTask_Fast import AutoEscortTask_Fast
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
                    "黎瑟：超级飞枪80护送",
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
            "拆解": AutoExpulsion,
            # "拆解": AutoDismantle, # 尚未实现
        }
        
        # 默认任务映射
        self.DEFAULT_TASK_MAPPING = {
            "自动70级皎皎币本": Auto70jjbTask,
            "自动飞枪80护送（无需巧手）【需要游戏处于前台】": AutoEscortTask,
            "黎瑟：超级飞枪80护送": AutoEscortTask_Fast,
            "使用外部移动逻辑自动打本": ImportTask
        }
        
        self.monitor_thread = None
        self.current_sub_task = None
        self.next_task_class = None
        self.next_task_module = None 
        self.finished_tasks = set()
        self.last_check_hour = -1
        self.lock = threading.Lock()
        self.force_check = False 
    
    def run(self):
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self.monitor_loop, name="AutoScheduleMonitor")
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        logger.info("主任务循环开始，等待调度指令...")

        while True:
            # 1. 获取下一个要执行的任务
            task_class = self.get_next_task()
            
            if not task_class:
                self.sleep(1)
                continue
                
            # 2. 执行子任务 (在主线程执行)
            self.execute_sub_task(task_class)
            
            # 3. 检查自身是否被停止
            if not self.enabled:
                break
    
    def get_next_task(self):
        with self.lock:
            return self.next_task_class

    def execute_sub_task(self, task_class):
        try:
            task = self.get_task_by_class(task_class)
            self.current_sub_task = task
            
            # 执行前置操作：重置页面状态
            self.reset_ui_state(task_class.__name__)
            
            logger.info(f"开始执行子任务: {task_class.__name__}")
            # 确保任务启用
            task.enable()
            # 在主线程运行任务
            task.run()
            
            # 任务自然结束（未被disable中断）
            logger.info(f"子任务自然结束: {task_class.__name__}")
            self.handle_task_finished(task_class)
            
        except TaskDisabledException:
            logger.info(f"子任务已停止 (被调度打断): {task_class.__name__}")
        except Exception as e:
            logger.error(f"子任务执行出错: {e}")
            self.sleep(5) 
        finally:
            self.current_sub_task = None

    def handle_task_finished(self, task_class):
        # 判断是否为默认任务
        default_task_name = self.config.get("默认任务")
        default_task_class = self.DEFAULT_TASK_MAPPING.get(default_task_name)
        
        if task_class != default_task_class:
            self.finished_tasks.add(task_class)
            logger.info(f"任务 {task_class.__name__} 加入已完成列表")
        else:
            logger.info(f"默认任务 {task_class.__name__} 自然结束，不加入黑名单")
        
        # 任务完成后立即触发一次检查，以便调度下一个任务
        self.force_check = True

    def monitor_loop(self):
        logger.info("监控线程启动")
        # 启动时先检查一次
        self.check_and_update_plan()
        
        now = datetime.now()
        if now.minute == 0:
            self.last_check_hour = now.hour

        while self.enabled:
            now = datetime.now()
            should_check = False
            
            # 1. 整点检查
            if now.minute == 0 and now.second >= 10 and now.hour != self.last_check_hour:
                logger.info(f"整点触发检查: {now}")
                self.last_check_hour = now.hour
                # 新的一小时，是否清空已完成任务？根据需求决定，暂时保持原逻辑不清空或手动清空
                # self.finished_tasks.clear() 
                should_check = True
                
            # 2. 强制检查 (任务结束触发)
            if self.force_check:
                should_check = True
                self.force_check = False
                
            if should_check:
                self.check_and_update_plan()
                
            time.sleep(1)
            
    def check_and_update_plan(self):
        try:
            new_task_class, new_module_key = self.calculate_target_task()
            
            with self.lock:
                # 如果计划的任务发生变化
                if new_task_class and (new_task_class != self.next_task_class or new_module_key != self.next_task_module):
                    logger.info(f"任务计划变更: {self.next_task_class.__name__ if self.next_task_class else 'None'} -> {new_task_class.__name__}")
                    self.next_task_class = new_task_class
                    self.next_task_module = new_module_key
                    
                    # 如果当前有正在运行的任务，且不是新计划的任务，则停止它
                    # 注意：如果只是同一任务的不同模块（re-run），也可能需要重启？
                    # 简化逻辑：只要类变了，或者强制重启，就disable
                    
                    if self.current_sub_task:
                        if isinstance(self.current_sub_task, new_task_class) and new_module_key == 'default':
                             # 如果是默认任务且正在运行，通常不需要打断，除非有更高优先级任务
                             # 但这里已经是变更了才会进这个if，所以直接打断
                             pass
                        
                        logger.info("停止当前运行的任务以应用新计划...")
                        self.current_sub_task.disable()
        except Exception as e:
            logger.error(f"调度检查出错: {e}")

    def calculate_target_task(self):
        """
        请求API并计算当前应该执行的任务
        返回: (TaskClass, ModuleKey)
        """
        API_URL = "https://wiki.ldmnq.com/v1/dna/instanceInfo"
        HEADERS = {"game-alias": "dna"}
        
        try:
            logger.info(f"开始请求API: {API_URL}")
            response = requests.get(API_URL, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                logger.error(f"API返回错误代码: {data.get('code')}")
                return self.get_default_task_info()

            instance_info_list = data.get("data", [])
            if not isinstance(instance_info_list, list):
                 logger.error("API返回的data不是列表格式")
                 return self.get_default_task_info()
            
            # 1. 解析委托（模块）优先级配置
            commission_config = self.config.get("委托", "角色>武器>MOD")
            commission_order = [x.strip() for x in commission_config.split(">") if x.strip()]
            
            name_map = {"角色": "role", "武器": "weapon", "MOD": "mod"}
            sorted_modules = [name_map[name] for name in commission_order if name in name_map]
            
            if not sorted_modules:
                logger.info("未配置有效的委托模块优先级")
                return self.get_default_task_info()

            # 2. 解析关卡（任务）优先级配置
            level_config = self.config.get("关卡", "探险/无尽>驱离>拆解")
            level_order = [x.strip() for x in level_config.split(">") if x.strip()]
            task_priority_map = {name: i for i, name in enumerate(level_order)}

            module_index_map = {"role": 0, "weapon": 1, "mod": 2}
            tasks_to_execute = []

            # 3. 遍历排序后的模块
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

            # 排序
            tasks_to_execute.sort(key=lambda x: x["priority"])
            
            # 4. 找到第一个未完成的任务
            for task in tasks_to_execute:
                if task['class'] not in self.finished_tasks:
                    logger.info(f"匹配到任务: {task['name']} (Module: {task['module_key']})")
                    return task['class'], task['module_key']
            
            logger.info("所有匹配的任务均已完成，执行默认任务")
            return self.get_default_task_info()
            
        except Exception as e:
            logger.error(f"请求API或处理数据失败: {e}")
            return self.get_default_task_info()

    def get_default_task_info(self):
        default_task_name = self.config.get("默认任务")
        if default_task_name and default_task_name in self.DEFAULT_TASK_MAPPING:
            return self.DEFAULT_TASK_MAPPING[default_task_name], "default"
        return None, None

    def disable(self):
        """
        当任务被手动停止时调用（重写 BaseTask.disable）。
        """
        logger.info("AutoScheduleTask 被手动停止")
        
        # 1. 停止当前子任务
        if self.current_sub_task:
            logger.info("停止当前子任务...")
            self.current_sub_task.disable()
            
        # 2. 调用父类逻辑 (设置 enabled=False 等)
        super().disable()

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
            if task_name == "AutoEscortTask" or task_name == "Auto70jjbTask" or task_name == "AutoEscortTask_Fast":
                self.click_relative_random(0.11, 0.16, 0.19, 0.18)
                self.sleep(1) 
           

            if task_name == "AutoEscortTask" or task_name == "AutoEscortTask_Fast":
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


        
