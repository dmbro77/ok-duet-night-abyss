from qfluentwidgets import FluentIcon
import time
import cv2

from ok import Logger, TaskDisabledException
from src.tasks.CommissionsTask import CommissionsTask, QuickMoveTask, Mission
from src.tasks.DNAOneTimeTask import DNAOneTimeTask

logger = Logger.get_logger(__name__)


class AutoExploration(DNAOneTimeTask, CommissionsTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.description = "半自动"
        self.default_config.update({
            '轮次': 3,
            '任务超时时间': 120,
        })
        self.config_description.update({
            '轮次': '打几个轮次',
            '任务超时时间': '超时后将发出提示',
        })
        self.setup_commission_config()
        self.name = "自动探险"
        self.action_timeout = 10
        self.quick_move_task = QuickMoveTask(self)
        
    def run(self):
        DNAOneTimeTask.run(self)
        try:
            return self.do_run()
        except TaskDisabledException as e:
            pass
        except Exception as e:
            logger.error('AutoExploration error', e)
            raise
        self.quick_move_task.stop()

    def do_run(self):
        self.find_serum()
        self.init_param()
        self.load_char()
        _start_time = time.time()
        _wait_next_wave = False
        _skill_time = 0
        while True:
            if self.in_team():
                self.progressing = self.find_serum()
                if self.progressing:
                    self.quick_move_task.stop()
                    _skill_time = self.use_skill(_skill_time)
                    if not _wait_next_wave and time.time() - _start_time >= self.config.get('任务超时时间', 120):
                        _wait_next_wave = True
                        self.log_info('任务超时', notify=True)
                        self.soundBeep()
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
                _start_time = time.time()
                _wait_next_wave = False

            self.sleep(0.2)

    def init_param(self):
        self.current_round = -1
        self.quick_move_task.stop()

    def stop_func(self):
        self.get_round_info()
        if self.current_round >= self.config.get('轮次', 3):
            return True
        
    def find_serum(self):
        return bool(self.find_one('serum_icon'))
