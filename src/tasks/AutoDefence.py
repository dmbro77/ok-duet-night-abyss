from qfluentwidgets import FluentIcon
import time
import cv2
import re

from ok import Logger, TaskDisabledException, Box
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.CommissionsTask import CommissionsTask, Mission, QuickMoveTask

logger = Logger.get_logger(__name__)


class AutoDefence(DNAOneTimeTask, CommissionsTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.description = "半自动"
        self.default_config.update({
            '轮次': 3,
            '波次超时时间': 90,
        })
        self.config_description = {
            '轮次': '打几个轮次',
            '波次超时时间': '超时后将发出提示',
        }
        self.setup_commission_config()
        self.name = "自动扼守"
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
        while True:
            if self.in_team():
                self.get_wave_info()
                if self.current_wave != -1:
                    self.quick_move_task.stop()
                    if self.current_wave != _wave:
                        _wave = self.current_wave
                        _wave_start = time.time()
                        _wait_next_wave = False

                    if not _wait_next_wave and time.time() - _wave_start >= self.config.get('波次超时时间', 120):
                        self.log_info('任务超时', notify=True)
                        self.soundBeep()
                        _wait_next_wave = True

                    if not _wait_next_wave:
                        _skill_time = self.use_skill(_skill_time)
                else:
                    self.quick_move_task.run()
            
            _status = self.handle_mission_interface(stop_func=self.stop_func)
            if _status == Mission.START:
                self.log_info('任务完成', notify=True)
                self.soundBeep()
                self.init_param()
            elif _status == Mission.STOP:
                self.restart_mission()
                self.log_info('任务中止，已重启', notify=True)
                self.soundBeep()
                self.init_param()
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
