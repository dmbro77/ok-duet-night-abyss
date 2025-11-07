from qfluentwidgets import FluentIcon
import re
import time
import win32con
import win32gui
import cv2

from ok import Logger, TaskDisabledException, Box
from ok import find_boxes_by_name
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.CommissionsTask import CommissionsTask, Mission, QuickMoveTask
from src.tasks.BaseCombatTask import BaseCombatTask

logger = Logger.get_logger(__name__)


class Auto70jjbTask(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.description = "全自动"
        self.default_config.update({
            '轮次': 1,
            '波次超时时间': 120,
        })
        self.config_description = {
            '轮次': '打几个轮次',
            '波次超时时间': '超时后将重启',
        }
        self.setup_commission_config()
        self.name = "自动70级皎皎币本"
        self.action_timeout = 10
        self.quick_move_task = QuickMoveTask(self)
        
    def run(self):
        DNAOneTimeTask.run(self)
        try:
            return self.do_run()
        except TaskDisabledException as e:
            pass
        except Exception as e:
            logger.error('AutoDefence error', e)
            raise
        self.quick_move_task.stop()

    def do_run(self):
        self.init_param()
        self.load_char()
        _wave = -1
        _wait_next_wave = False
        _skill_time = 0
        _wave_start = 0
        self.quick_move_task.stop()
        if self.in_team():
            self.open_in_mission_menu()
            self.sleep(0.5)
        while True:
            if self.in_team():
                self.get_wave_info()
                if self.current_wave != -1:
                    if self.current_wave != _wave:
                        _wave = self.current_wave
                        _wave_start = time.time()
                        _wait_next_wave = False

                    if not _wait_next_wave and time.time() - _wave_start >= self.config.get('波次超时时间', 120):
                        self.log_info('任务超时')
                        self.open_in_mission_menu()
                        self.sleep(0.5)
                        _wait_next_wave = True

                    if not _wait_next_wave:
                        _skill_time = self.use_skill(_skill_time)
            
            _status = self.handle_mission_interface(stop_func=self.stop_func)
            if _status == Mission.START or _status == Mission.STOP:
                if _status == Mission.STOP:
                    self.restart_mission()
                    self.log_info('任务中止，已重启')
                    self.init_param()
                else:
                    self.log_info('任务完成')
                self.wait_until(self.in_team, time_out=30)                
                win32gui.SendMessage(self.hwnd.hwnd, win32con.WM_KEYDOWN, 0xA4, 0)
                self.sleep(2)
                self.walk_to_aim()
                win32gui.SendMessage(self.hwnd.hwnd, win32con.WM_KEYUP, 0xA4, 0)
                _wave_start = time.time()
            elif _status == Mission.CONTINUE:
                self.log_info('任务继续')
                self.wait_until(self.in_team, time_out=30)
                self.current_wave = -1
            self.sleep(0.2)

    def init_param(self):
        self.stop_mission = False
        self.current_round = -1
        self.current_wave = -1
        self.quick_move_task.stop()

    def stop_func(self):
        self.get_round_info()
        n = self.config.get('轮次', 3)
        if n == 1 or self.current_round >= n:
            return True

    def find_next_hint(self, x1, y1, x2, y2, s, box_name='hint_text'):
        texts = self.ocr(box=self.box_of_screen(x1, y1, x2, y2, hcenter=True),
                         target_height=540, name=box_name)
        fps_text = find_boxes_by_name(texts,
                                      re.compile(s, re.IGNORECASE))
        if fps_text:
            return True
        return False
        
    def find_and_click(self, x1, y1, x2, y2, s):
        if self.find_next_hint(x1, y1, x2, y2, s):
            self.click((x1+x2)/2, (y1+y2)/2, after_sleep=0.5)
            return True
        return False
    
    def wait_hint(self, x1, y1, x2, y2, hint, timeout=2):
        if self.wait_until(lambda: self.find_next_hint(x1, y1, x2, y2, hint), time_out=timeout):
            self.sleep(0.2)
            return True
        return False
    
    def reset_and_transport(self):
        self.open_in_mission_menu()
        self.sleep(0.5)
        self.click(0.73, 0.92, after_sleep=0.5)
        self.click(0.35, 0.03, after_sleep=0.5)
        self.click(0.35, 0.03, after_sleep=0.5)
        self.click(0.60, 0.32, after_sleep=0.5)
        self.click(0.59, 0.56, after_sleep=1)
        
    def walk_to_aim(self):   
        if self.find_next_hint(0.18,0.52,0.23,0.55,r'保护目标'):
            #无电梯
            self.send_key_down('w')
            self.sleep(8.5)
            self.send_key_up('w')
            self.send_key_down('a')
            self.sleep(0.2)
            self.send_key_up('a')
            self.middle_click(after_sleep=0.5)
            self.send_key_down('w')
            self.sleep(6)
            self.send_key_down('d')
            self.sleep(5.6)
            self.send_key_up('d')
            self.sleep(23)
            self.send_key_up('w')
            self.sleep(0.2)
            #分支1直接到达，分支2继续往前走，复位不可
            if self.find_next_hint(0.46,0.37,0.51,0.41,r'保护目标'):               
                self.send_key_down('w')
                self.sleep(7.5)
                self.send_key('space', down_time=0.2, after_sleep=2.7)
                self.send_key_up('w')
            return             
        self.send_key('w', down_time=12.1, after_sleep=0.2)
        if self.find_next_hint(0.77,0.34,0.83,0.38,r'保护目标'):
            #电梯右
            self.sleep(0.5)
            self.send_key('space',down_time=0.2,after_sleep=0.2)
            self.send_key('w', down_time=0.8,after_sleep=0.2)
            self.send_key('d', down_time=0.2,after_sleep=0.2)
            self.middle_click(after_sleep=0.5)
            self.send_key('w', down_time=3.4,after_sleep=0.2)
            self.send_key_down('a')
            self.sleep(3.4)
            self.send_key_down('w')
            self.sleep(2.6)
            self.send_key_up('a')
            self.sleep(2.1)
            self.send_key('a', down_time=0.4,after_sleep=6.4)
            self.send_key_up('w')
            self.sleep(0.2)
            self.send_key('a', down_time=6.1,after_sleep=0.2)
            self.send_key('w', down_time=8,after_sleep=0.2)
            #两种地图均可复位到达
            self.reset_and_transport()
            return            
        if self.find_next_hint(0.17,0.39,0.23,0.43,r'保护目标'):
            #电梯左
            self.sleep(0.5)
            self.send_key('space',down_time=0.2,after_sleep=0.2)
            self.send_key_down('w')
            self.sleep(3.8)
            self.send_key('d', down_time=0.4, after_sleep=3)
            self.send_key('d', down_time=0.4, after_sleep=6.7)
            self.send_key_up('w')
            self.sleep(0.2)
            self.send_key('a', down_time=0.2, after_sleep=0.2)
            self.middle_click(after_sleep=0.5)
            self.send_key_down('w')
            self.sleep(8.7)
            self.send_key('d', down_time=1, after_sleep=0.5)
            self.send_key('d', down_time=0.6, after_sleep=1.3)
            self.send_key('d', down_time=0.6, after_sleep=6.2)
            self.send_key('d', down_time=0.4, after_sleep=0.5)
            self.send_key('d', down_time=0.4, after_sleep=4.5)
            self.send_key_up('w')
            #两种地图均可复位到达
            self.reset_and_transport()
            return            
        #电梯中
        self.sleep(0.5)
        self.send_key('space',down_time=0.2,after_sleep=0.2)
        self.send_key_down('w')
        self.sleep(4.8)
        self.send_key('d', down_time=1.8, after_sleep=9.6)
        self.send_key('d', down_time=3.4, after_sleep=3.4)
        self.send_key_up('w')
        self.sleep(0.2)
        self.send_key('a', down_time=1.9, after_sleep=0.2)
        self.send_key('w', down_time=6, after_sleep=0.2)
        #两种地图均可复位到达
        self.reset_and_transport()
        #finish
        return          