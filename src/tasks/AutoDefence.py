from qfluentwidgets import FluentIcon
import time

from ok import Logger, TaskDisabledException, Box
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.CommissionsTask import CommissionsTask, Mission, QuickMoveTask

logger = Logger.get_logger(__name__)
_default_movement = lambda: False


class AutoDefence(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动扼守"
        self.description = "半自动"
        self.group_name = "半自动"
        self.group_icon = FluentIcon.VIEW

        self.default_config.update({
            '轮次': 3,
        })
        
        self.setup_commission_config()
        
        self.config_description.update({
            "轮次": "打几个轮次",
            "超时时间": "波次超时后将发出提示",
        })

        self.action_timeout = 10
        self.quick_move_task = QuickMoveTask(self)
        self.external_movement = lambda: False

    def config_external_movement(self, func: callable, config: dict):
        if callable(func):
            self.external_movement = func
        else:
            self.external_movement = lambda: False
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
            logger.error("AutoDefence error", e)
            raise

    def do_run(self):
        self.init_param()
        self.load_char()
        _wave = -1
        _wait_next_wave = False       
        _wave_start = 0
        if self.external_movement is not _default_movement and self.in_team():
            self.open_in_mission_menu()
        while True:
            if self.in_team():
                self.get_wave_info()
                if self.current_wave != -1:
                    if self.current_wave != _wave:
                        _wave = self.current_wave
                        _wave_start = time.time()
                        _wait_next_wave = False
                        self.quick_move_task.reset()

                    if not _wait_next_wave and time.time() - _wave_start >= self.config.get("超时时间", 120):
                        if self.external_movement is not _default_movement:
                            self.log_info("任务超时")
                            self.open_in_mission_menu()
                        else:
                            self.log_info_notify("任务超时")
                            self.soundBeep()
                            _wait_next_wave = True

                    if not _wait_next_wave:
                        self.skill_time = self.use_skill(self.skill_time)
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
                    if not self.wait_until(lambda: self.current_wave != -1, post_action=self.get_wave_info, time_out=time_out):
                        self.log_info(f"超时重开")
                        self.open_in_mission_menu()
                    else:
                        self.log_info(f"战斗开始")
                else:
                    self.log_info_notify("任务开始")
                    self.soundBeep()
            elif _status == Mission.STOP:
                self.quit_mission()
                self.init_param()
                self.log_info("任务中止")
            elif _status == Mission.CONTINUE:
                self.wait_until(self.in_team, time_out=30)
                self.log_info("任务继续")
                self.current_wave = -1

            self.sleep(0.2)

    def init_param(self):
        self.current_round = -1
        self.current_wave = -1
        self.skill_time = 0

    def stop_func(self):
        self.get_round_info()
        n = self.config.get("轮次", 3)
        if n == 1 or self.current_round >= n:
            return True
