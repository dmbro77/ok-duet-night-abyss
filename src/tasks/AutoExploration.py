from qfluentwidgets import FluentIcon
import time
import cv2

from ok import Logger, TaskDisabledException
from src.tasks.CommissionsTask import CommissionsTask, QuickMoveTask, Mission
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.DNAOneTimeTask import DNAOneTimeTask

logger = Logger.get_logger(__name__)
_default_movement = lambda: False


class AutoExploration(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动探险"
        self.description = "半自动"
        self.group_name = "半自动"
        self.group_icon = FluentIcon.VIEW

        self.default_config.update({
            '轮次': 3,
        })

        self.setup_commission_config()

        self.config_description.update({
            '轮次': '打几个轮次',
            '超时时间': '超时后将发出提示',
        })
        
        self.action_timeout = 10
        self.quick_move_task = QuickMoveTask(self)
        self.external_movement = _default_movement

    def config_external_movement(self, func: callable, config: dict):
        if callable(func):
            self.external_movement = func
        else:
            self.external_movement = _default_movement
        self.config.update(config)
        
    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position()
        self.set_check_monthly_card()
        try:
            return self.do_run()
        except TaskDisabledException as e:
            pass
        except Exception as e:
            logger.error("AutoExploration error", e)
            raise

    def do_run(self):
        self.init_param()
        self.load_char()
        _wait_next_round = False        
        _start_time = 0
        if self.external_movement is not _default_movement and self.in_team():
            self.open_in_mission_menu()
        while True:
            if self.in_team():
                self.progressing = self.find_serum()
                if self.progressing:
                    if _start_time == 0:
                        _start_time = time.time()
                        _wait_next_round = False
                        self.quick_move_task.reset()
                    self.skill_time = self.use_skill(self.skill_time)
                    if not _wait_next_round and time.time() - _start_time >= self.config.get("超时时间", 120):
                        if self.external_movement is not _default_movement:
                            self.log_info("任务超时")
                            self.open_in_mission_menu()
                        else:
                            self.log_info_notify("任务超时")
                            self.soundBeep()
                            _wait_next_round = True
                else:
                    self.quick_move_task.run()

            _status = self.handle_mission_interface(stop_func=self.stop_func)
            if _status == Mission.START:
                self.wait_until(self.in_team, time_out=30)
                self.sleep(2)
                self.init_param()
                if self.external_movement is not _default_movement:
                    self.log_info("任务开始")
                    self.external_movement()
                    time_out = 10
                    self.log_info(f"外部移动执行完毕，等待战斗开始，{time_out}秒后超时")
                    if not self.wait_until(self.find_serum, time_out=time_out):
                        self.log_info(f"超时重开")
                        self.open_in_mission_menu()
                    else:
                        self.log_info(f"战斗开始")
                else:
                    self.log_info_notify("任务开始")
                    self.soundBeep()
                _start_time = 0
            elif _status == Mission.STOP:
                self.quit_mission()
                self.log_info("任务中止")
            elif _status == Mission.CONTINUE:
                self.wait_until(self.in_team, time_out=30)
                self.log_info("任务继续")
                _start_time = 0

            self.sleep(0.2)

    def init_param(self):
        self.current_round = -1
        self.skill_time = 0

    def stop_func(self):
        self.get_round_info()
        if self.current_round >= self.config.get("轮次", 3):
            return True

    def find_serum(self):
        return bool(self.find_one("serum_icon"))
