from ok import Logger, TaskDisabledException
from qfluentwidgets import FluentIcon
import re
import time

from src.tasks.CommissionsTask import CommissionsTask, Mission
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.trigger.AutoMazeTask import AutoMazeTask
from src.tasks.trigger.AutoRouletteTask import AutoRouletteTask
from src.tasks.BaseCombatTask import BaseCombatTask

logger = Logger.get_logger(__name__)
DEFAULT_ACTION_TIMEOUT = 10


class MapDetectionError(Exception):
    """地图识别错误异常"""
    pass

class AutoDismantle(DNAOneTimeTask, CommissionsTask, BaseCombatTask):
    """全自动密函拆解"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.group_icon = FluentIcon.CAFE
        self.name = "全自动密函拆解"
        self.description = "全自动，需高范围水母，到达地点会自动释放终结技"
        self.group_name = "全自动2"
        self.default_config.update({
            '解密失败自动重开': True,
        })
        self.config_description.update({
            '解密失败自动重开': '不重开时会发出声音提示',
        })

        substrings_to_remove = ["轮次",'超时时间']
        keys_to_delete = [key for key in self.default_config for sub in substrings_to_remove if sub in key]
        for key in keys_to_delete:
            self.default_config.pop(key, None)
        
        # 地图检测点和执行函数的映射字典
        self.map_configs = {
            # 分岔路地图
            "分岔路": { 
                "track_point": (0.45, 0.26, 0.50, 0.36),
                "execute_func": self.execute_one_map
            },
            # 长通道地图
            "长通道": {
                "track_point": (0.37, 0.35, 0.42, 0.43),
                "execute_func": self.execute_two_map
            },
            # 大谷地地图
            "大谷地": {
                "track_point": (0.65, 0.28, 0.71, 0.38),
                "execute_func": self.execute_three_map
            }
        }

    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position(save_current_pos=False)
        self.set_check_monthly_card()
        try:
            return self.do_run()
        except TaskDisabledException:
            self.handle_mission_end()
            pass
        except Exception as e:
            logger.error('AutoDismantle error', e)
            raise

    def do_run(self):
        self.init_all()
        self.load_char()
        # self.handle_mission_start()
        # self.execute_common_map()
        # return

        if self.in_team():
            self.open_in_mission_menu()

        while True:
            try:
                _status = self.handle_mission_interface(stop_func=self.stop_func)
                if _status == Mission.START:
                    self.wait_until(self.in_team, time_out=30)
                    self.handle_mission_start()
                elif _status == Mission.STOP:
                    pass
                elif _status == Mission.CONTINUE:
                    pass

                self.sleep(0.1)
            except MapDetectionError as e:
                # 地图识别错误，记录日志并重试
                self.log_info(f"地图识别错误: {e}，重新开始任务")
                self.runtime_state['failed_round'] += 1
                if self.current_map in self.runtime_state['failed_map']:
                    self.runtime_state['failed_map'][self.current_map] += 1
                else:
                    self.runtime_state['failed_map']['地图识别失败'] += 1
                self.update_task_statistics()
                # 尝试退出或者重启
                if self.in_team():
                    self.give_up_mission()

    def init_all(self):
        self.runtime_state = {
            "start_time": time.time(),
            'current_round':0,
            'failed_round':0,
            'end_time':0,
            # 各地图失败次数
            "failed_map": {
                "分岔路": 0,
                "长通道": 0,
                "大谷地": 0,
                "地图识别失败": 0
            }
        }
        self.current_map = None
        
    def handle_mission_end(self):
        self.runtime_state['end_time'] = time.time()
        self.update_task_statistics()
        self.info_set("任务耗时",f'{self.runtime_state["end_time"] - self.runtime_state["start_time"]:.2f}s')

    def update_task_statistics(self):
        self.info_set("任务统计",f'{self.runtime_state["current_round"]}/{self.runtime_state["current_round"]+self.runtime_state["failed_round"]}')
        self.info_set("失败统计",f'分岔路：{self.runtime_state["failed_map"]["分岔路"]}    长通道：{self.runtime_state["failed_map"]["长通道"]}    大谷地：{self.runtime_state["failed_map"]["大谷地"]}')

    def handle_mission_start(self):
        self.log_info("任务开始")
        self.walk_to_aim(delay=2)
        self.log_info("外部移动执行完毕，任务完成，等待10s超时")
        self.sleep(5)
        timeout, now = 5, time.time()
        while time.time() - now < timeout:
            if not self.in_team():
                self.log_info("拆解任务完成")
                # 增加对应地图的成功统计
                self.runtime_state['current_round'] += 1
                self.update_task_statistics()  
                return
            self.sleep(1)
                
        self.log_info("任务超时未完成，任务失败")
        if self.current_map in self.runtime_state['failed_map']:
            self.runtime_state['failed_map'][self.current_map] += 1
        self.runtime_state['failed_round'] += 1
        self.update_task_statistics()
        self.send_key('esc')
      


    def stop_func(self):
        pass

    def walk_to_aim(self, delay=0):
        try:
            # self.send_key_down("lalt")
            self.sleep(delay)
            
            self.execute_common_map()
            # self.sleep(60)
            current_map = self.detect_current_map()

            logger.info(f"当前地图类型：{current_map}")

            # 如果检测到未知地图，抛出地图识别错误
            if current_map == "未知地图":
                raise MapDetectionError("无法识别当前地图类型")
            
          
            self.current_map = current_map
            # 执行对应地图的移动逻辑
            if current_map in self.map_configs:
                self.log_info(f"识别到地图类型：{current_map}，开始执行移动逻辑")
                return self.map_configs[current_map]["execute_func"]()
            else:
                # 这种情况理论上不应该发生，因为current_map是从map_configs中检测出来的
                raise MapDetectionError(f"地图配置不一致，检测到地图[{current_map}]但找不到对应的执行函数")
        finally:
            pass
            # self.send_key_up("lalt")
    
    def detect_current_map(self):
        """检测当前地图类型"""
        detected_maps = []
        
        for map_name, config in self.map_configs.items():
            x1, y1, x2, y2 = config["track_point"]
            if self.find_track_point(x1, y1, x2, y2):
                detected_maps.append(map_name)
                self.log_info(f"检测到地图标记：{map_name} at ({x1}, {y1}, {x2}, {y2})")
        
        if len(detected_maps) == 0:
            logger.warning("地图检测失败：未检测到任何已知的地图标记")
            return "未知地图"
        elif len(detected_maps) == 1:
            return detected_maps[0]
        else:
            # 检测到多个地图标记，记录日志并返回第一个检测到的
            logger.warning(f"地图检测冲突：同时检测到多个地图标记 {detected_maps}，使用第一个检测到的地图")
            return detected_maps[0]
    
    def execute_common_map(self):
        """执行公共地图的移动逻辑"""
        self.log_info("执行公共地图移动")
        self.sleep(0.572)
        self.send_key_down("w")
        self.sleep(0.432)
        self.send_key_down(self.get_dodge_key())
        self.sleep(0.454)
        self.send_key_down("a")
        self.sleep(0.312)
        self.send_key_up("w")
        self.sleep(0.414)
        self.send_key_up(self.get_dodge_key())
        self.sleep(0.622)
        self.send_key_down("w")
        self.sleep(0.248)
        self.send_key_up("w")
        self.sleep(0.434)
        self.send_key_up("a")
        self.sleep(0.2)
        self.middle_click()
        self.sleep(0.8)

    def execute_one_map(self):
        """执行分岔路地图的移动逻辑"""
        self.log_info("执行分岔路地图移动")

        self.sleep(0.875)
        self.send_key_down("w")
        self.sleep(0.448)
        self.send_key_down(self.get_dodge_key())
        self.sleep(1.366)
        self.send_key_down("a")
        self.sleep(0.160)
        self.send_key_up("a")
        self.sleep(1.145)
        self.send_key_down("a")
        self.sleep(0.152)
        self.send_key_up("a")
        self.sleep(2.706)
        self.send_key_down("a")
        self.sleep(0.132)
        self.send_key_up("a")
        self.sleep(0.892)
        self.send_key_down("a")
        self.sleep(0.083)
        self.send_key_up("a")
        self.sleep(0.320)
        self.send_key_up(self.get_dodge_key())
        self.sleep(0.707)
        self.send_key_down("space")
        self.sleep(0.128)
        self.send_key_up("space")
        self.sleep(0.128)
        self.send_key_down("space")
        self.sleep(0.094)
        self.send_key_up("space")
        self.sleep(0.290)
        self.send_key_down("a")
        self.sleep(0.021)
        self.send_key_up("w")
        self.sleep(0.033)
        self.send_key_up("a")
        self.sleep(1.024)
        self.send_key_down("w")
        self.sleep(0.096)
        self.send_key_up("w")
        
        # 交互点 F
        self.sleep(0.4)
        self.send_key(self.get_interact_key(), down_time=0.1, after_sleep=0.8)
        if not self.try_solving_puzzle():
            return True

        self.sleep(0.2)
        self.send_key_down("a")
        self.sleep(0.394)
        self.send_key_down(self.get_dodge_key())
        self.sleep(1.633)
        self.send_key_up(self.get_dodge_key())
        self.sleep(0.050)
        self.send_key_up("a")
        self.send_key_down("w")
        self.sleep(0.678)
        self.send_key_down("space")
        self.sleep(0.168)
        self.send_key_up("space")
        self.sleep(0.065)
        self.send_key_down("space")
        self.sleep(0.132)
        self.send_key_up("space")
        self.sleep(1.814)
        self.send_key_down("d")
        self.sleep(0.016)
        self.send_key_up("w")
        self.sleep(1.110)
        self.send_key_down("w")
        self.sleep(0.030)
        self.send_key_up("d")
        self.sleep(2.104)
        self.send_key_up("w")
        self.sleep(0.2)
        self.send_key_down("space")
        self.sleep(0.112)
        self.send_key_up("space")
        self.sleep(0.121)
        self.send_key_down("space")
        self.sleep(0.132)
        self.send_key_up("space")
        self.sleep(0.233)
        self.send_key_down(self.get_ultimate_key())
        self.sleep(0.091)
        self.send_key_up(self.get_ultimate_key())
        self.sleep(1)
        return True

    def execute_two_map(self):
        """执行长通道地图的移动逻辑"""
        self.log_info("执行长通道地图移动")
        
        self.sleep(0.4)
        self.send_key_down("w")
        self.sleep(1.926)
        self.send_key_down("d")
        self.sleep(0.020)
        self.send_key_up("w")
        self.sleep(0.445)
        self.send_key_down(self.get_dodge_key())
        self.sleep(2.078)
        self.send_key_up(self.get_dodge_key())
        self.sleep(1.365)
        self.send_key_down("w")
        self.sleep(0.054)
        self.send_key_up("d")
        self.sleep(2.259)
        self.send_key_up("w")
        self.sleep(0.013)
        self.send_key_down("a")
        self.sleep(4.739)
        self.send_key_up("a")
        self.sleep(0.5)
        self.send_key(self.get_interact_key(), down_time=0.1)
        self.sleep(0.5)
        self.send_key_down("s")
        self.sleep(0.142)
        self.send_key_up("s")
        self.sleep(0.1)
        self.send_key(self.get_interact_key(), down_time=0.1)
        self.sleep(0.217)
        self.send_key_down("a")
        self.sleep(0.1)
        self.send_key(self.get_interact_key(), down_time=0.1)
        self.sleep(0.135)
        self.send_key_up("a")
        
        # 交互点 F
        self.sleep(0.1)
        self.send_key(self.get_interact_key(), down_time=0.1, after_sleep=0.8)
        if not self.try_solving_puzzle():
            return True
            
        self.sleep(0.2)
        self.send_key_down("w")
        self.sleep(0.451)
        self.send_key_down(self.get_dodge_key())
        self.sleep(0.729)
        self.send_key_up(self.get_dodge_key())
        self.sleep(0.294)
        self.send_key_down("d")
        self.sleep(0.112)
        self.send_key_up("w")
        self.sleep(0.891)
        self.send_key_down("w")
        self.sleep(0.031)
        self.send_key_up("d")
        self.sleep(1.834)
        self.send_key_up("w")
        self.sleep(0.598)
        self.send_key_down(self.get_ultimate_key())
        self.sleep(0.137)
        self.send_key_up(self.get_ultimate_key())
        self.sleep(1)
        return True


    def execute_three_map(self):
        """执行大谷地地图的移动逻辑"""
        self.log_info("执行大谷地地图移动")
        
        self.sleep(0.450)
        self.send_key_down("w")
        self.sleep(1.216)
        self.send_key_down(self.get_dodge_key())
        self.sleep(0.164)
        self.send_key_up(self.get_dodge_key())
        self.sleep(0.302)
        self.send_key_down("d")
        self.sleep(0.132)
        self.send_key_up("w")
        self.sleep(1.702)
        self.send_key_down("w")
        self.sleep(0.031)
        self.send_key_up("d")
        self.sleep(2.645)
        self.send_key_up("w")
        self.sleep(0.2)
        self.send_key_down("d")
        self.sleep(0.085)
        self.send_key_up("d")
        
        # 交互点 F
        self.sleep(0.4)
        self.send_key(self.get_interact_key(), down_time=0.1, after_sleep=0.8)
        if not self.try_solving_puzzle():
            return True
            
        self.sleep(0.2)
        self.send_key_down("d")
        self.sleep(0.512)
        self.send_key_down(self.get_dodge_key())
        self.sleep(1.162)
        self.send_key_up("d")
        self.sleep(0.012)
        self.send_key_up(self.get_dodge_key())
        self.sleep(0.180)
        self.send_key_down("w")
        self.sleep(0.481)
        self.send_key_down(self.get_dodge_key())
        self.sleep(2.716)
        self.send_key_up(self.get_dodge_key())
        self.sleep(0.021)
        self.send_key_up("w")
        self.sleep(0.705)
        self.send_key_down("a")
        self.sleep(0.618)
        self.send_key_up("a")
        self.sleep(0.430)
        self.send_key_down(self.get_ultimate_key())
        self.sleep(0.102)
        self.send_key_up(self.get_ultimate_key())
        self.sleep(1)
        return True

    def find_track_point(self, x1, y1, x2, y2) -> bool:
        box = self.box_of_screen_scaled(2560, 1440, 2560*x1, 1440*y1, 2560*x2, 1440*y2, name="find_track_point", hcenter=True)
        result = super().find_track_point(threshold=0.7, box=box)
        # 调试信息：记录检测结果
        logger.debug(f"地图检测点 ({x1}, {y1}, {x2}, {y2}) 检测结果: {result}")
        if not result:
            result = self.wait_ocr(
                threshold=0.7, 
                box=box,
                match=re.compile(f'.*操作装置.*'),
                time_out=1
            )
            if result:
                result = result[0]
        return result        
        
    def try_solving_puzzle(self):
        maze_task = self.get_task_by_class(AutoMazeTask)
        roulette_task = self.get_task_by_class(AutoRouletteTask)
        if not self.wait_until(
            self.in_team, 
            post_action = lambda: self.send_key(self.get_interact_key(), after_sleep=0.1),
            time_out = 1.5
        ):
            maze_task.run()
            roulette_task.run()
            if not self.wait_until(self.in_team, time_out=1.5):           
                if self.config.get("解密失败自动重开", True):                    
                    self.log_info("未成功处理解密，等待重开")
                    self.open_in_mission_menu()
                else:
                    self.log_info_notify("未成功处理解密，请求人工接管")
                    self.soundBeep()
                    self.wait_until(self.in_team, time_out = 60)
                return False               
        return True
        
    
