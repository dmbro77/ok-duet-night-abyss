import re
import time
import cv2
from enum import Enum

from src.tasks.BaseDNATask import isolate_white_text_to_black
from src.tasks.BaseCombatTask import BaseCombatTask

class Mission(Enum):
    START = 1
    CONTINUE = 2
    STOP = 3
    GIVE_UP = 4

class CommissionsTask(BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_round = -1
        self.current_wave = -1

    def setup_commission_config(self):
        self.default_config.update({
            '委托手册': '不使用',
            '使用技能': '不使用',
            '技能释放频率': 5,
            '启用自动穿引共鸣': True,
            '发出声音提醒': True
        })
        self.config_description.update({
            '技能释放频率': '毎几秒释放一次技能',
            '启用自动穿引共鸣': '在需要跑图时时启用触发任务的自动穿引共鸣',
            '发出声音提醒': '在需要时发出声音提醒'
        })
        self.config_type['委托手册'] = {'type': 'drop_down', 'options': ['不使用', '100%', '200%', '800%', '2000%']}
        self.config_type['使用技能'] = {'type': 'drop_down', 'options': ['不使用', '战技', '终结技']}

    def find_quit_btn(self, threshold = 0):
        continue_box = self.box_of_screen_scaled(2560, 1440, 798, 972, 855, 1026, name="quit_mission", hcenter=True)
        template = self.get_feature_by_name('quit_icon')
        scaled_mat = cv2.resize(template.mat, None, fx=1.1, fy=1.1, interpolation=cv2.INTER_LINEAR)
        return self.find_one(template=scaled_mat, box=continue_box, threshold=threshold)
    
    def find_continue_btn(self, threshold = 0):
        continue_box = self.box_of_screen_scaled(2560, 1440, 1600, 972, 1654, 1028, name="continue_mission", hcenter=True)
        template = self.get_feature_by_name('start_icon')
        scaled_mat = cv2.resize(template.mat, None, fx=1.1, fy=1.1, interpolation=cv2.INTER_LINEAR)
        return self.find_one(template=scaled_mat, box=continue_box, threshold=threshold)
    
    def find_bottom_start_btn(self, threshold = 0):
        return self.find_start_btn(threshold=threshold, box=self.box_of_screen_scaled(2560, 1440, 2100, 1272, 2145, 1316, name="start_mission", hcenter=True))
    
    def find_esc_menu(self, threshold = 0):
        return self.find_one('quit_big_icon', threshold=threshold)
    
    def open_in_mission_menu(self, time_out: float = 10, raise_if_not_found: bool = True):
        if self.find_esc_menu():
            return True
        found = False
        start = time.time()
        while time.time() - start < time_out:
            self.send_key('esc')
            if self.wait_until(self.find_esc_menu, time_out=2, raise_if_not_found=False):
                found = True
                break
        else:
            if raise_if_not_found:
                raise Exception("未找到任务菜单")
        return found
    
    def start_mission(self, timeout=10):
        box = self.box_of_screen_scaled(2560, 1440, 2100, 1272, 2145, 1316, name="start_mission", hcenter=True)
        start_time = time.time()
        while time.time() - start_time < 20:
            self.wait_click_start_btn(time_out=0.25, box=box, raise_if_not_found=False)
            self.wait_click_retry_btn(time_out=0.25, raise_if_not_found=False)
            self.sleep(0.5)
            if self.find_start_btn():
                break
        else:
            raise Exception("等待开始任务超时")
        self.choose_drop_rate(timeout)

    def restart_mission(self, timeout=10):
        action_timeout = self.safe_get("action_timeout", timeout)
        quit_btn = self.wait_until(self.find_quit_btn, time_out=action_timeout, raise_if_not_found=True)
        self.sleep(0.5)
        self.click_until(
            click_func=lambda: self.click_box(quit_btn),
            check_func=lambda: not self.find_quit_btn(),
            time_out=action_timeout
        )
        self.start_mission(action_timeout)

    def give_up_mission(self, timeout=10):
        action_timeout = self.safe_get("action_timeout", timeout)
        box = self.box_of_screen_scaled(2560, 1440, 1310, 788, 1352, 830, name="start_mission", hcenter=True)
        self.open_in_mission_menu()

        self.click_until(
            click_func=lambda: self.click_relative(0.95, 0.91),
            check_func=lambda: self.find_start_btn(box=box),
            time_out=action_timeout
        )
        self.sleep(0.5)
        self.click_until(
            click_func=lambda: self.wait_click_start_btn(box=box, time_out=0.2, raise_if_not_found=False),
            check_func=lambda: not self.find_start_btn(box=box),
            time_out=action_timeout
        )

    def continue_mission(self, timeout=10):
        if self.in_team():
            return False
        action_timeout = self.safe_get("action_timeout", timeout)
        continue_btn = self.wait_until(self.find_continue_btn, time_out=action_timeout, raise_if_not_found=True)
        self.click_until(
            click_func=lambda: self.click_box(continue_btn),
            check_func=lambda: not self.find_continue_btn(),
            time_out=action_timeout
        )
        self.sleep(0.5)
        start_box = self.box_of_screen_scaled(2560, 1440, 1074, 943, 1120, 990, name="continue_mission", hcenter=True)
        self.click_until(
            click_func=lambda: self.wait_click_start_btn(time_out=0.2, box=start_box, raise_if_not_found=False),
            check_func=lambda: not self.find_start_btn(box=start_box),
            time_out=action_timeout
        )
        return True
        
    def choose_drop_rate(self, timeout=10):
        action_timeout = self.safe_get("action_timeout", timeout)
        self.choose_drop_rate_item()
        self.click_until(
            click_func=lambda: self.wait_click_start_btn(time_out=0.2, raise_if_not_found=False),
            check_func=lambda: not self.find_start_btn(),
            time_out=action_timeout
        )

    def choose_drop_rate_item(self):
        if not hasattr(self, "config"):
            return
        drop_rate = self.config.get('委托手册', '不使用')
        if drop_rate == '不使用':
            return
        elif drop_rate == '100%':
            self.click_relative(0.40, 0.56)
        elif drop_rate == '200%':
            self.click_relative(0.50, 0.56)
        elif drop_rate == '800%':
            self.click_relative(0.59, 0.56)
        elif drop_rate == '2000%':
            self.click_relative(0.68, 0.56)
        self.log_info(f"使用委托手册: {drop_rate}")
        self.sleep(0.5)

    def use_skill(self, skill_time):
        if not hasattr(self, "config"):
            return
        if self.config.get('使用技能', '不使用') != '不使用' and time.time() - skill_time >= self.config.get('技能释放频率', 5):
            skill_time = time.time()
            if self.config.get('使用技能') == '战技':
                self.get_current_char().send_combat_key()
            elif self.config.get('使用技能') == '终结技':
                self.get_current_char().send_ultimate_key()
        return skill_time

    def get_round_info(self):
        if self.in_team():
            return
        self.sleep(0.5)
        round_info_box = self.box_of_screen_scaled(2560, 1440, 531, 517, 618, 602, name="round_info", hcenter=True)
        texts = self.ocr(box=round_info_box)
        if texts:
            prev_round = self.current_round
            try:
                self.current_round = int(texts[0].name)
            except:
                return
            if prev_round != self.current_round:
                self.info_set("当前轮次", self.current_round)

    def get_wave_info(self):
        if not self.in_team():
            return
        mission_info_box = self.box_of_screen_scaled(2560, 1440, 275, 372, 360, 470, name="mission_info", hcenter=True)
        texts = self.ocr(box=mission_info_box, frame_processor=isolate_white_text_to_black, match=re.compile(r'\d/\d'))
        if texts and len(texts) == 1:
            prev_wave = self.current_wave
            try:
                if (m := re.match(r'(\d)/\d', texts[0].name)):
                    self.current_wave = int(m.group(1))
            except:
                return
            if prev_wave != self.current_wave:
                self.info_set("当前波次", self.current_wave)

    def wait_until_get_wave_info(self):
        self.log_info('等待波次信息...')
        while self.current_wave == -1:
            self.get_wave_info()
            self.sleep(0.2)
        
    def handle_mission_interface(self, stop_func=lambda: False):
        if self.in_team():
            return False
        if self.find_bottom_start_btn() or self.find_retry_btn():
            self.start_mission()
            return Mission.START
        elif self.find_continue_btn():
            if stop_func():
                return Mission.STOP
            self.continue_mission()
            return Mission.CONTINUE
        elif self.find_esc_menu():
            self.give_up_mission()
            self.sleep(2)
            return Mission.GIVE_UP
        elif self.find_start_btn():
            self.choose_drop_rate()
            return Mission.START
        return False

class QuickMoveTask:
    def __init__(self, owner: CommissionsTask):
        self.owner = owner
        self.owner._move_task = None
        
    def run(self):
        if not hasattr(self.owner, "config"):
            return
        if self.owner.config.get('启用自动穿引共鸣', False):
            if not self.owner._move_task:
                from src.tasks.AutoMoveTask import AutoMoveTask
                self.owner._move_task = self.owner.get_task_by_class(AutoMoveTask)
            self.owner._move_task.run()

    def stop(self):
        if self.owner._move_task:
            self.owner._move_task.stop()
        
