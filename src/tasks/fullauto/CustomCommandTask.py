from qfluentwidgets import FluentIcon
import time
import random
import re
import os
import cv2
import numpy as np

from pathlib import Path
from PIL import Image
from ok import Logger, TaskDisabledException
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.CommissionsTask import CommissionsTask, Mission, QuickAssistTask

logger = Logger.get_logger(__name__)

MOUSE_VAL_TO_PIXELS = 10



class CustomCommandTask(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "使用自定义指令自动打本"
        self.description = "全自动"
        self.group_name = "全自动2"
        self.group_icon = FluentIcon.CAFE

        self.setup_commission_config()

        self.default_config.update({
            "快速继续挑战": True,
            "关闭抖动": False,
            "关闭抖动锁定在窗口范围": False,
            "自定义指令": "#0.5\n",
            "自定义指令工具": "" 
                + "使用/编辑鼠标移动指令时 请在 OK-DNA 设置里配置游戏内灵敏度以便分享\n" 
                + "\n" 
                + "重置位置: ! \n" 
                + "前进5秒: w5 \n" 
                + "前冲5秒: w>5 \n" 
                + "飞枪(1.67~1.75): L0.3#0.4 \n" 
                + "\n\n\n" 
                + "星屑落ちて　華は散っても\n" 
                + "キラめく舞台に　生まれて変わる\n" 
                + "新たな私は　未知なる運命\n" 
                + "新たな私は　まだ見ぬ戯曲\n" 
                + "愛城華恋は　舞台に一人\n" 
                + "愛城華恋は　次の舞台へ",
            "自定义指令随机波动": False,
            "随机游走": False,
            "随机游走幅度": 1.0,
        })
        self.config_description.update({
            "快速继续挑战": "R键快速继续挑战，跳过结算动画。",
            "自定义指令":  ""
                + "任意小写字母: 对应按键\n"
                + "等待: # \n" 
                + "交互: + \n"
                + "跳跃: _ \n" 
                + "移动: w a s d wa ws sa sd \n" 
                + "移动冲刺: [wasd]{1,2}> \n" 
                + "鼠标点击: L R \n"
                + "鼠标移动: W A S D (50 := 90°) \n"
                + "闪避后跳: < \n" 
                + "螺旋飞跃: @ \n" 
                + "重置位置: ! \n" 
                + "\t\t\t\t",
            "自定义指令工具": "记事本 / 剪切板 \n"
                +"可用于记录自定义指令 \n" 
                + "\t\t\t\t",
            "自定义指令随机波动": "每次移动持续时间随机 -/+ 0.0% ~ 7.5%",
            "随机游走": "是否在任务中随机移动",
            "随机游走幅度": "单次走动最大持续时间（秒）",
        })
        self.config_type["挂机模式"] = {
            "type": "drop_down",
            "options": ["开局重置角色位置", "原地待机"],
        }

        self.action_timeout = 10
        
        self.skill_tick = self.create_skill_ticker()
        self.random_walk_tick = self.create_random_walk_ticker()

    def run(self):
        if self.config.get("关闭抖动", False):
            mouse_jitter_setting = self.afk_config.get("鼠标抖动")
            self.afk_config.update({"鼠标抖动": False}) 
        if self.config.get("关闭抖动锁定在窗口范围", False):
            mouse_jitter_lock_setting = self.afk_config.get("鼠标抖动锁定在窗口范围")
            self.afk_config.update({"鼠标抖动锁定在窗口范围": False}) 
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position(save_current_pos=False)
        self.set_check_monthly_card()
        try:
            return self.do_run()
        except TaskDisabledException:
            pass
        except Exception as e:
            logger.error("AutoExpulsion error", e)
            raise
        finally:
            if self.config.get('关闭抖动', False):
                self.afk_config.update({"鼠标抖动": mouse_jitter_setting})
                self.afk_config.update({"鼠标抖动锁定在窗口范围": mouse_jitter_lock_setting})
                try:
                    self.release_all_move_keys()
                except Exception as e:
                    logger.error("AutoExpulsion key release error", e)
                    raise
    
    def release_all_move_keys(self):
        """释放所有移动相关按键，防止卡键"""
        keys = ['w', 'a', 's', 'd', 'lalt', 
                self.get_dodge_key(), 
                self.get_spiral_dive_key(), 
                self.get_interact_key(), 
            ]
        for k in keys:
            self.send_key_up(k)

    def do_run(self):
        self.count = 0
        self.runtime_state = {}
        self.custom_commands = []
        self.init_all()
        self.load_char()
        while True:
            if self.in_team():
                self.handle_in_mission()
            elif (self.config.get("快速继续挑战", False) 
                and self.current_round ==0
                and not self.wait_until(lambda: self.in_team(), time_out=0.3)
            ):
                self.send_key(key="r", down_time=0.050)

            _status = self.handle_mission_interface(stop_func=self.stop_func)
            if _status == Mission.START:
                self.wait_until(self.in_team, time_out=30)
                self.init_all()
                self.handle_mission_start()
            elif _status == Mission.STOP:
                self.log_info("任务中止")
                self.quit_mission()
            elif _status == Mission.CONTINUE:
                self.log_info("任务继续")
                self.init_for_next_round()
                self.wait_until(self.in_team, time_out=self.action_timeout)

            self.sleep(0.1)

    def init_all(self):
        self.init_for_next_round()
        self.skill_tick.reset()
        self.current_round = 0

    def init_for_next_round(self):
        self.init_runtime_state()

    def init_runtime_state(self):
        self.info_set("完成轮次", self.count)
        self.get_round_info()
        self.info_set("当前轮次", self.current_round)
        self.reset_wave_info()
        self.info_set("上轮耗时", f"{(time.time() - self.runtime_state.get("round_time", time.time())):.1f}秒")
        self.runtime_state = {"start_time": 0, "round_time": time.time(),
                              "wave_start_time": 0, "wave": -1, "wait_next_wave": False}
        self.random_walk_tick.reset()

    def handle_in_mission(self):
        if self.runtime_state["start_time"] == 0:
            self.runtime_state["start_time"] = time.time()
            self.count += 1
        
        self.get_wave_info()
        if self.current_wave != -1:
            # 如果是新的波次，重置状态
            if self.current_wave != self.runtime_state["wave"]:
                self.runtime_state.update(
                    {"wave": self.current_wave, "wave_start_time": time.time(), "wait_next_wave": False})
                
            if not self.runtime_state["wait_next_wave"] and time.time() - self.runtime_state[
                "wave_start_time"] >= self.config.get("超时时间", 120):
                self.log_info("任务超时")
                self.give_up_mission()
                return

        elif time.time() - self.runtime_state["start_time"] >= self.config.get("超时时间", 120):
            logger.info("已经超时，重开任务...")
            self.give_up_mission()
            return

        self.random_walk_tick()
        self.skill_tick()

    def handle_mission_start(self):
        self.sleep(2)
        self.log_info("任务开始")
        self.parse_custom_commands()
        self.execute_custom_commands()
        self.skill_tick()
        
    def create_random_walk_ticker(self):
        """创建一个随机游走的计时器函数。"""
        def action():
            if not self.config.get("随机游走", False):
                return
            duration = random.uniform(0, 1) * self.config.get("随机游走幅度", 1.0)
            direction = random.choice(["w", "a", "s", "d"])
            self.send_key(direction, down_time=duration)

        return self.create_ticker(action, interval=5, interval_random_range=(0.8, 2))

    def stop_func(self):
        self.get_round_info()
        n = self.config.get("轮次", 3)
        if self.current_round >= n:
            return True

    def parse_custom_commands(self):
        """Parse the custom command string from config into self.custom_commands."""
        self.custom_commands = []
        cmd = str(self.config.get("自定义指令", "")).strip().replace(' ', '').replace('\n', '')
        self.log_debug("自定义指令: " + cmd)
        if not cmd: return
        pattern = r":([^()]+)\(([^()]+)\)|([^:()]+)"
        for m in re.finditer(pattern, cmd):
            func, func_cmd, std_cmd = m.groups()
            fail_cmd = None
            if func_cmd: func_cmd, fail_cmd = str(func_cmd).split(',', 1) if ',' in func_cmd else (func_cmd, None)
            self.log_debug(f"已提取自定义指令: {func}, {func_cmd}, {std_cmd}")
            self.custom_commands.append({
                'actions': self.parse_actions(func_cmd if func_cmd else std_cmd),
                'actions_fail': self.parse_actions(fail_cmd) if fail_cmd else None,
                'func': func,
            })

    def parse_actions(self, cmd):
        """Parse 'cmd' strings into executable actions."""
        # "cmd -> {'type': str, ...}"
        actions = []
        pattern = r"(#\d+(?:\.\d+)?)|([A-Za-z]{1,5}+(?:>)?\d*(?:\.\d+)?)|(!|<|_|@|\+)"
        token = re.compile(pattern)
        for m1 in token.finditer(str(cmd)):
            t = m1.group(0)
            if not t: continue
            match(t[0]):
                case '#':
                    dur=self.try_parse_float(t[1:])
                    actions.append({'type': 'wait', 'dur': dur})
                case '!': actions.append({'type': 'reset'})
                case '_': actions.append({'type': 'key', 'key': 'space', 'dur': 0.050})
                case '+': actions.append({'type': 'key', 'key': self.get_interact_key(), 'dur': 0.050})
                case '<': actions.append({'type': 'key', 'key': self.get_dodge_key(), 'dur': 0.050})
                case '@': actions.append({'type': 'key', 'key': self.get_spiral_dive_key(), 'dur': 0.050})
                case _:
                    m2 = re.match(r'([A-Za-z]{1,5}+(?:>)?)(\d*(?:\.\d+)?)', t)
                    if not m2: continue
                    sym = m2.group(1)
                    num = m2.group(2)
                    val = self.try_parse_float(num)
                    match(sym):
                        case 'STOP': actions.append({'type': 'STOP'})
                        case 'EXIT': actions.append({'type': 'EXIT'})
                        case 'SKIP': actions.append({'type': 'SKIP'})
                        case 'TICK': actions.append({'type': 'TICK'})
                        case 'L': actions.append({'type': 'mouse', 'key': 'left', 'dur': val})
                        case 'R': actions.append({'type': 'mouse', 'key': 'right', 'dur': val})
                        case 'A': actions.append({'type': 'move', 'direction': 'X', 'angel': -val})
                        case 'D': actions.append({'type': 'move', 'direction': 'X', 'angel': val})
                        case 'W': actions.append({'type': 'move', 'direction': 'Y', 'angel': -val})
                        case 'S': actions.append({'type': 'move', 'direction': 'Y', 'angel': val})
                        case _: 
                            if (sym[-1] == '>'): 
                                actions.append({'type': 'key', 'key': sym[:-1], 'dur': val, 'sprint': True})
                            else: 
                                actions.append({'type': 'key', 'key': sym, 'dur': val})
        return actions
    
    def try_parse_float(self, str, default_val = 1.000):
        val = default_val
        try:
            val = float(str)
        except Exception:
            pass
        return val

    def execute_custom_commands(self):
        """Execute the parsed custom actions sequentially."""
        if not self.custom_commands: return
        for command in self.custom_commands:
            actions = command.get("actions", "")
            func = command.get("func", "")
            if func and not self.execute_cc_func(func):
                actions = command.get("actions_fail", "")
                if not actions: continue
            if not actions: return
            for act in actions:
                self.log_debug(f"执行自定义指令: {act}")
                match(act['type']):
                    case 'STOP': 
                        self.give_up_mission()
                        raise TaskDisabledException
                    case 'EXIT': 
                        self.give_up_mission()
                        return
                    case 'SKIP': return
                    case 'TICK': self.skill_tick()
                    case 'wait': self.sleep(act['dur'])
                    case 'reset': self.reset_and_transport()
                    case 'mouse':
                        self.mouse_down(key=act['key'])
                        self.sleep(act['dur'])
                        self.mouse_up(key=act['key'])
                    case 'move':
                        if act.get('direction') == 'X':
                            self.move_mouse_relative(act['angel'] * MOUSE_VAL_TO_PIXELS, 0)
                        elif act.get('direction') == 'Y':
                            self.move_mouse_relative(0, act['angel'] * MOUSE_VAL_TO_PIXELS)
                    case 'key':
                        dur = act['dur']
                        if self.config.get("自定义指令随机波动", False):
                            dur = dur * random.uniform(1 - 0.075, 1 + 0.075)
                        if len(act['key']) in (1, 2):
                            for key in act['key']:
                                self.send_key_down(key)
                                self.sleep(0.050)
                                dur -= 0.050
                            if act.get('sprint', False): self.send_key(key=self.get_dodge_key(), down_time=dur)
                            else: self.sleep(dur)
                            for key in act['key']:
                                self.send_key_up(key)
                                self.sleep(0.050)
                        elif act['key']:
                            try:
                                self.send_key(act['key'], down_time=dur)
                            except Exception:
                                pass
    
    def execute_cc_func(self, func) -> bool:
        op, arg = func[0], func[1:]
        self.log_info(f"执行 cc_func: op - {op}, arg - {arg}")
        if arg: arg, param = str(arg).split(',', 1) if ',' in arg else (arg, None)
        match(op):
            case 'R': # if round
                round = self.try_parse_float(arg, default_val=0)
                return round == self.count
            case 'M': # if match img
                img_foler, target_id = arg[:-1], arg[-1]
                if param: map_id = self.cc_func_match_img(map_foler=img_foler, 
                    min_threshold=self.try_parse_float(param, default_val=0.8))
                else: map_id = self.cc_func_match_img(map_foler=img_foler)
                return target_id == map_id
            case ':':
                # ::(comment) for comment
                return False
        return False
    
    def cc_func_match_img(self, map_foler, min_threshold=0.800):
        path = Path.cwd()
        imgs = self.load_png_files(fr'{path}\mod\CustomCommand\img\{map_foler}')
        
        box = self.box_of_screen_scaled(2560, 1440, 1, 1, 2559, 1439, name="full_screen", hcenter=True)
        frame = self.frame
        self.shared_frame = frame
        cropped_screen = box.crop_frame(frame)
        screen_gray = cv2.cvtColor(cropped_screen, cv2.COLOR_BGR2GRAY)
        max_id = None
        best_threshold = min_threshold
        
        for name, template_gray in imgs.items():
            result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            _, threshold, _, _, = cv2.minMaxLoc(result)
            self.log_debug(f"MAP: {name} (conf={threshold:.4f})")
            if threshold > best_threshold:
                best_threshold = threshold
                max_id = name

        if max_id is not None:
            self.log_info(f"成功匹配: {max_id} (conf={best_threshold:.4f})")
            max_id = max_id[-1]

        return max_id

    def load_png_files(self, folder_path):
        png_files = {}

        if not os.path.exists(folder_path):
            self.log_info(f"文件夹 '{folder_path}' 不存在，将执行无图匹配逻辑。")
            return png_files

        for filename in os.listdir(folder_path):
            if filename.lower().endswith('.png'):
                file_path = os.path.join(folder_path, filename)
                try:
                    pil_img = Image.open(file_path)
                    img_array = np.array(pil_img)
                    if len(img_array.shape) == 3:
                        template = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                    else:
                        template = img_array

                    if template is None:
                        raise ValueError(f"图像转换失败: {file_path}")

                    # 兼容性处理：Python 3.9+ 才支持 removesuffix，低版本用切片
                    key_name = filename.removesuffix(".png") if hasattr(filename, "removesuffix") else filename[:-4]

                    png_files[key_name] = template
                    self.log_info(f"成功加载(已转灰度): {filename}")

                except Exception as e:
                    self.log_error(f"加载失败 {filename}", e)
        png_files = {key: png_files[key] for key in sorted(png_files.keys(), key=lambda x: (len(x), x))}
        return png_files
