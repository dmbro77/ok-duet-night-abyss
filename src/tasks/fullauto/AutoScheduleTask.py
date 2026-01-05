import requests
from qfluentwidgets import FluentIcon
import time
import threading
import re
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

logger = Logger.get_logger('================')

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
                ]
            },
            "默认任务副本等级": {
                "type": "drop_down",
                 "options": [
                    "5", "10", "15", "20", "30", "35", "40", "50", "60", "70", "80", "100"
                ]
            },
        }

        self.config_description = {
            "默认任务": "当没有匹配的委托密函任务时，自动执行此任务\n任务基于已有的任务执行，请对设置的默认任务做好相应配置",
            "默认任务副本类型": "选择要执行的任务类型，根据选择的默认任务进行设置",
            "默认任务副本等级":"选择需要刷取的副本等级，根据选择的默认任务和副本类型进行设置",
            "密函委托优先级": "使用 > 分隔优先级，越靠前优先级越高，只能填写角色、武器、MOD。\n例如：角色>武器>MOD",
            "关卡类型优先级": "使用 > 分隔优先级，越靠前优先级越高，仅支持探险/无尽、驱离。\n例如：探险/无尽>驱离",
        }

        # 任务映射关系
        self.TASK_MAPPING = {
            "探险/无尽": AutoExploration_Fast,
            "驱离": AutoExpulsion,
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
        self.next_task_name = None 
        self.finished_tasks = set()
        self.stats = [] # 存储统计信息 [{"time": "...", "task": "...", "status": "..."}]
        self.last_check_hour = -1
        self.lock = threading.Lock()
        self.force_check = False 
    
    def run(self):
        if not self.config.get("默认任务副本类型"):
            self.info_set("自动密函:默认任务副本类型", "未配置")
            return
        if not self.config.get("默认任务副本等级"):
            self.info_set("自动密函:默认任务副本等级", "未配置")
            return
        if not self.config.get("默认任务"):
            self.info_set("自动密函:默认任务", "未配置")
            return
        if not self.config.get('密函委托优先级'):
            self.info_set("自动密函:密函委托优先级", "未配置")
            return
        if not self.config.get('关卡类型优先级'):
            self.info_set("自动密函:关卡类型优先级", "未配置")
            return
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self.monitor_loop, name="AutoScheduleMonitor")
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        logger.info("主任务循环开始，等待调度指令...")

        self.stats = []

        while True:
            # 在检查的时候不执行
            if self.force_check:
                self.sleep(1)
                return
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
        task_name = task_class.__name__
        start_time = datetime.now()
        start_str = start_time.strftime("%H:%M:%S")
        
        # 记录到统计
        current_stat = {
            "task": self.next_task_name,
            "module": self.next_task_module,
            "start_time": start_str,
            "end_time": "",
            "status": "执行中"
        }
        self.stats.append(current_stat)
        
        # 更新UI
        self.info_set("自动密函:当前任务", self.next_task_name)
        self.info_set("自动密函:开始时间", start_str)
        self.info_set("自动密函:任务状态", "执行中")
        self._update_task_summary_ui()

        try:
            task = self.get_task_by_class(task_class)            
            original_info_set = task.info_set
            task.info_set = self.info_set
            self.current_sub_task = task
            
            # 执行前置操作：重置页面状态
            self.reset_ui_state(task_name)
            
            logger.info(f"开始执行子任务: {self.next_task_name}")
            # 确保任务启用
            task.enable()
            # 在主线程运行任务
            task.run()
            
            # 任务自然结束（未被disable中断）
            logger.info(f"子任务自然结束: {self.next_task_name}")
            
            current_stat["status"] = "已完成"
            self.info_set("自动密函:任务状态", "已完成")
            
            self.handle_task_finished(task_class)
            
        except TaskDisabledException:
            logger.info(f"子任务已停止 (被调度打断): {self.next_task_name}")
            current_stat["status"] = "已停止"
            self.info_set("自动密函:任务状态", "已停止")
        except Exception as e:
            logger.error(f"子任务执行出错: {e}")
            current_stat["status"] = "出错"
            self.info_set("自动密函:任务状态", "出错")
            self.sleep(5) 
        finally:
            end_time = datetime.now()
            end_str = end_time.strftime("%H:%M:%S")
            current_stat["end_time"] = end_str
            self.info_set("自动密函:结束时间", end_str)
            
            # 更新任务汇总
            self._update_task_summary_ui()
            
            self.current_sub_task = None
            if 'task' in locals() and task is not self:
                task.info_set = original_info_set

            # 任务执行完成后等待5秒，确保监控线程已处理完下一个任务
            # self.sleep(5)    

    def _update_task_summary_ui(self):
        """
        更新任务统计汇总UI
        格式：任务名称，开始时间1-结束时间1，开始时间2-结束时间2...
        """
        # 按任务名称分组
        task_groups = {}
        for stat in self.stats:
            name = stat["task"]+"("+stat["module"]+")"
            if name not in task_groups:
                task_groups[name] = []
            
            time_range = f"{stat['start_time']}-{stat['end_time']}"
            task_groups[name].append(time_range)
        
        # 格式化输出字符串
        summary_lines = []
        for name, ranges in task_groups.items():
            ranges_str = "，".join(ranges)
            summary_lines.append(f"{name}，{ranges_str}")
            
        summary_text = "\n".join(summary_lines)
        self.info_set("自动密函:任务总计", summary_text)


    def handle_task_finished(self, task_class):
        # 判断是否为默认任务
        default_task_name = self.config.get("默认任务")
        default_task_class = self.DEFAULT_TASK_MAPPING.get(default_task_name)
        
        if task_class != default_task_class:
            # 使用 模块+任务类名 作为唯一标识，区分不同模块下的相同任务
            task_key = f"{self.next_task_module}_{task_class.__name__}"
            self.finished_tasks.add(task_key)
            logger.info(f"任务 {self.next_task_name} ({self.next_task_module}) 加入已完成列表: {task_key}")
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
            logger.info("监控线程运行中...")
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
            new_task_class, new_module_key, new_task_name = self.calculate_target_task()
            
            with self.lock:
                # 如果计划的任务发生变化
                if new_task_class and (new_task_class != self.next_task_class or new_module_key != self.next_task_module):
                    logger.info(f"任务计划变更: {self.next_task_class.__name__ if self.next_task_class else 'None'} -> {new_task_class.__name__}")
                    self.next_task_class = new_task_class
                    self.next_task_module = new_module_key
                    self.next_task_name = new_task_name
                    
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
        返回: (TaskClass, ModuleKey, TaskName)
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
            logger.info(f"API返回的实例信息列表: {instance_info_list}")
            if not isinstance(instance_info_list, list):
                 logger.error("API返回的data不是列表格式")
                 return self.get_default_task_info()
            
            # 1. 解析委托（模块）优先级配置
            commission_config = self.config.get("密函委托优先级", "角色>武器>MOD")
            commission_order = [x.strip() for x in commission_config.split(">") if x.strip()]
            
            module_index_map = {"角色": 0, "武器": 1, "MOD": 2}

            # 过滤出有效的模块名
            sorted_modules = [name for name in commission_order if name in module_index_map]

            
            if not sorted_modules:
                logger.info("未配置有效的密函委托优先级")
                return self.get_default_task_info()

            # 2. 解析关卡（任务）优先级配置
            level_config = self.config.get("关卡类型优先级", "探险/无尽>驱离")
            level_order = [x.strip() for x in level_config.split(">") if x.strip()]
            task_priority_map = {name: i for i, name in enumerate(level_order)}

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
                task_key = f"{task['module_key']}_{task['class'].__name__}"
                if task_key not in self.finished_tasks:
                    logger.info(f"匹配到任务: {task['name']} (Module: {task['module_key']})")
                    return task['class'], task['module_key'], task['name']
            
            logger.info("未匹配到可执行的密函任务，执行默认任务")
            return self.get_default_task_info()
            
        except Exception as e:
            logger.error(f"请求API或处理数据失败: {e}")
            return self.get_default_task_info()

    def get_default_task_info(self):
        default_task_name = self.config.get("默认任务")
        if default_task_name and default_task_name in self.DEFAULT_TASK_MAPPING:
            return self.DEFAULT_TASK_MAPPING[default_task_name], "default", default_task_name
        return None, None, default_task_name

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
        # # 3. 结束监控线程, super().disable() 会将 self.enabled 标记为 False
        # # monitor_thread 中的循环 ( while self.enabled: ) 会在当前循环结束后（最多等待 1 秒 time.sleep ）检测到标记变化并退出循环
        # if self.monitor_thread and self.monitor_thread.is_alive():
        #     logger.info("等待监控线程结束...")
        #     self.monitor_thread.join()
        #     logger.info("监控线程已结束")   

    def reset_ui_state(self, task_name):
        """
        执行任务前的前置操作，重置页面到初始状态。
        """
        logger.info(f"执行前置操作：重置UI状态 ({task_name})")
        try:
            # 查找历练文本
            lilian = self.find_lilian()
            logger.debug(f"当前是否处于历练页面: {lilian is not None}")
            while not lilian:
                lilian = self.find_lilian()
                if lilian:
                    break
                self.send_key("esc")
                self.sleep(1)
                if self.in_team():
                    # 在副本中，执行退出副本操作
                    self.give_up_mission()
                # 副本刷取中密函耗尽，点击确定后在退出 
                if (letter_btn:=self.find_letter_interface()):
                    logger.info("密函耗尽，点击确认选择后，再退出副本")
                    # 密函耗尽，点击确认选择后，再退出副本
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
                    # 退出副本
                    self.give_up_mission()
            # 默认任务副本选择逻辑
            if task_name is not "AutoExploration_Fast" and task_name is not "AutoExpulsion": 
                self.switch_to_default_task()
                self.switch_to_task_level()
            # 密函本需要切换到密函页面
            else:     
                self.switch_to_letter()
            self.sleep(0.3)
            logger.info("UI状态重置完成")
        except Exception as e:
            logger.warning(f"UI状态重置可能未完全成功: {e}")


    # 切换到默认任务副本
    def switch_to_default_task(self):
        # 点击切换到委托
        self.click_relative_random(0.11, 0.16, 0.19, 0.18)
        self.sleep(1) 
        clicked  = False
        flag = 0
        default_task_type = self.config.get("默认任务副本类型")
        # width,height = self.get_screen_size()
        self.scroll_relative(0.5, 0.4, -1000)
        self.sleep(1)
        while not clicked and flag < 3:
            logger.info(f"滚动副本: {int(0.3*self.width)}")
            self.scroll_relative(0.5, 0.4, int(0.33*self.width))
            # self.swipe_relative(0.3, 0.5, 0.5, 0.5)
            # self.mouse_down(0.59*self.width, 0.50*self.height)
            # self.move(0.17*self.width,0.52*self.height)
            # self.mouse_up()
            
            self.sleep(1)
            logger.info(f"尝试匹配默认任务副本类型: {default_task_type.split(":")[1]}")
            match_box = self.ocr(
                box=self.box_of_screen_scaled(
                    2560, 1440, 2560 * 0.07, 1440 * 0.69, 2560 * 0.66, 1440 * 0.75,
                    name="weituo", hcenter=True
                ),
                match=re.compile(f'.*{default_task_type.split(":")[1]}.*') 
            )
            logger.info(f"匹配到的默认任务副本类型: {match_box}")
            if match_box:
                self.click_box_random(match_box[0])
                clicked = True
                break
            else:
                flag += 1        

    # 选择默认任务关卡等级
    def switch_to_task_level(self):
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
            if match_box:
                self.click_box_random(match_box[0])
                clicked = True
                break
            else:
                flag += 1        

    # 选择密函
    def switch_to_letter(self):
        # 密函本需要切换到密函页面
        self.click_relative_random(0.34, 0.15, 0.41, 0.18)
        self.sleep(1) 
        name = self.next_task_name
        box = None
        if self.next_task_module == '角色':
            box = self.box_of_screen_scaled(
                2560, 1440, 2560 * 0.07, 1440 * 0.051, 2560 * 0.16, 1440 * 0.77,
                name='guan_qia', hcenter=True
            )
        if self.next_task_module == '武器':
            box = self.box_of_screen_scaled(
                2560, 1440, 2560 * 0.28, 1440 * 0.051, 2560 * 0.38, 1440 * 0.77,
                name='guan_qia', hcenter=True
            )   
        if self.next_task_module == 'MOD':
            box = self.box_of_screen_scaled(
                2560, 1440, 2560 * 0.48, 1440 * 0.051, 2560 * 0.59, 1440 * 0.77,
                name='guan_qia', hcenter=True
            )     
        
        clicked  = False
        flag = 0      
        while not clicked and flag < 3:    
            text = self.wait_ocr(
                box=box,
                match=name,
                time_out=5,
                raise_if_not_found=True,
            )
            self.click_box_random(text[0])
            clicked = True

    # 查找历练文本
    def find_lilian(self):
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
            