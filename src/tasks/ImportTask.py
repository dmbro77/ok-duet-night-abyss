from qfluentwidgets import FluentIcon
import re
import time
import win32con
import win32gui
import cv2
import os
import json
import numpy as np

from pathlib import Path
from PIL import Image
from ok import Logger, TaskDisabledException, Box
from ok import find_boxes_by_name
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.CommissionsTask import CommissionsTask, Mission, QuickMoveTask
from src.tasks.BaseCombatTask import BaseCombatTask

from src.tasks.AutoDefence import AutoDefence

logger = Logger.get_logger(__name__)


class ImportTask(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.description = "全自动"
        self.config_type['外部文件夹'] = {
            "type": "drop_down",
            "options": self.load_direct_folder(f'{Path.cwd()}\mod'),
        }
        self.default_config.update({
            '轮次': 10,
            '超时时间': 120,
            '外部文件夹': ""
        })
        self.config_description = {
            '轮次': '如果是无尽关卡，选择打几个轮次',
            '超时时间': '战斗超时后将重启',
            '外部文件夹': '选择mod目录下的外部逻辑'
        }
        self.config_type['外部文件夹'] = {
            "type": "drop_down",
            "options": self.load_direct_folder(f'{Path.cwd()}\mod'),
        }
        self.setup_commission_config()
        self.default_config.pop("启用自动穿引共鸣", None)
        self.name = "使用外部移动逻辑自动打本"
        self.action_timeout = 10
        self.quick_move_task = QuickMoveTask(self)    
        
    def load_direct_folder(self, path):
        folders = []
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                folders.append(item)
        return folders
        
    def run(self):
        path = Path.cwd()
        self.script = self.process_json_files(f'{path}\mod\{self.config.get('外部文件夹')}\scripts')
        self.img = self.load_png_files(f'{path}\mod\{self.config.get('外部文件夹')}\map')
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position()
        try:
            return self.do_run()
        except TaskDisabledException as e:
            pass
        except Exception as e:
            logger.error('AutoDefence error', e)
            raise

    def do_run(self):
        self.init_param()
        self.load_char()
        _wave = -1
        _wait_next_wave = False
        _skill_time = 0
        _wave_start = 0
        if self.in_team():
            self.open_in_mission_menu()
            self.sleep(0.5)
        while True:
            if self.in_team():
                self.get_wave_info()
                if self.current_wave != -1:
                    if self.current_wave != _wave:
                        _wave = self.current_wave
                        _wait_next_wave = False
                _skill_time = self.use_skill(_skill_time)
                if time.time() - _wave_start >= self.config.get('超时时间', 180):
                    self.log_info('任务超时')
                    self.open_in_mission_menu()
                    self.sleep(0.5)
                    _wait_next_wave = True                       
            
            _status = self.handle_mission_interface(stop_func=self.stop_func)
            if _status == Mission.START or _status == Mission.STOP:
                if _status == Mission.STOP:
                    self.quit_mission()
                    self.log_info('任务中止')
                    self.init_param()
                    continue
                else:
                    self.log_info('任务完成')
                self.wait_until(self.in_team, time_out=30)                  
                self.sleep(2)
                self.walk_to_aim()
                _wave_start = time.time()
                self.current_wave = -1 
            elif _status == Mission.CONTINUE:
                self.log_info('任务继续')
                self.wait_until(self.in_team, time_out=30)
                self.current_wave = -1
                _wave_start = time.time()
            self.sleep(0.2)

    def foo(self):
        _to_do_task = self.get_task_by_class(AutoDefence)
        _to_do_task.config_external_movement(lambda: True, self.config)
        _to_do_task.do_run()
    
    def init_param(self):
        self.stop_mission = False
        self.current_round = -1
        self.current_wave = -1

    def stop_func(self):
        self.get_round_info()
        n = self.config.get('轮次', 3)
        if n == 1 or self.current_round >= n:
            return True
            
    def process_json_files(self, folder_path):
        json_files = {}   
        for filename in os.listdir(folder_path):
            if filename.endswith('.json'):
                file_path = os.path.join(folder_path, filename)          
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        json_files[filename.removesuffix(".json")] = data
                        self.log_info(f"成功加载: {file_path}")
                except Exception as e:
                    self.log_info(f"加载失败 {file_path}: {e}")
    
        return json_files
    
    def load_png_files(self, folder_path):
        png_files = {}  
        for filename in os.listdir(folder_path):
            if filename.lower().endswith('.png'):
                file_path = os.path.join(folder_path, filename)           
                try:
                    pil_img = Image.open(file_path)
                    img_array = np.array(pil_img)
                    template = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
                    if template is None:
                        raise FileNotFoundError(f"无法读取模板图像: {file_path}")
                    png_files[filename.removesuffix(".png")] = template
                    self.log_info(f"成功加载: {filename}")
                except Exception as e:
                    self.log_info(f"加载失败 {filename}: {e}") 
        png_files = {key: png_files[key] for key in sorted(png_files.keys(), key=lambda x: (len(x), x))}
        return png_files

    def walk_to_aim(self):
        former_index = None
        while True:
            start = time.time()        
            map_index = None 
            count = 0
            while map_index is None and time.time() - start < 5:    
                map_index, count = self.match_map(former_index)
                if count == 0:
                    return False
            if map_index is not None:            
                self.log_info(f'执行{map_index}')
                self.play_macro_actions(self.script[map_index]["actions"], self.script[map_index]["total_time"])
                former_index = map_index
            else:
                return False
        
    def match_map(self, index):
        box = self.box_of_screen_scaled(2560, 1440, 1, 1, 2559, 1439, name="full_screen", hcenter=True)
        count = 0
        max_conf = 0
        max_index = None

        for i, name in enumerate(self.img):
            if index is not None and not (index in name and len(name) - len(index) <= 3):
                continue
            if index == name:
                continue
            count += 1
            img = self.img[name]
            feature = None
            
            cropped = box.crop_frame(self.frame)
            gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)      
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            result = cv2.matchTemplate(gray, img, cv2.TM_CCOEFF_NORMED)
            _, threshold, _, _, = cv2.minMaxLoc(result)
            if threshold > max_conf:
                max_conf = threshold
                max_index = name  
            self.log_info(f"匹配: {name} confidence = {threshold}")
    #        feature = self.find_one(template=img, box=box, threshold=0.4)    
    #        feature = self.find_one(img, box=self.box_of_screen(0.18, 0.1, 0.82, 0.81),
    #                              threshold=0.65, frame_processor=binarize_for_matching)
    #        if feature is None:
    #            self.log_info(f"匹配: {name} confidence < 0.4")
    #            continue
    #        self.log_info(f"匹配: {name} confidence = {feature.confidence}")
    #        if feature is not None and feature.confidence > max_conf:
    #            max_conf = feature.confidence
    #            max_index = name
         
        if max_index != None:
            self.log_info(f"成功匹配: {max_index}")
        else:
            self.log_info(f"匹配失败")
        return max_index, count
    
    def play_macro_actions(self, actions, total_time):
        start = time.time()
        for i, action in enumerate(actions): 
            while time.time()-start < action['time']:
                self.next_frame()   
            self.execute_key_action(action)
        self.sleep(2)
                
    def execute_key_action(self, action):
        try:
            if action['type'] == "mouse_down":   
                self.mouse_down(key=action['button'])
            elif action['type'] == "mouse_up": 
                self.mouse_up(key=action['button'])
            elif action['type'] == "key_down":
                action['key'] = normalize_key(action['key'])
                self.send_key_down(action['key'])
            elif action['type'] == "key_up":
                action['key'] = normalize_key(action['key'])
                self.send_key_up(action['key'])
            else:
                raise
        except:
            self.log_info(f"不支持的按键-> type: {action['type']} key: {action['key']}")
            raise


def normalize_key(key: str) -> str:
    """
    将 'shift' (不区分大小写) 标准化为 'lshift'。
    """
    if isinstance(key, str) and key.lower() == 'shift':
        return 'lshift'
    return key