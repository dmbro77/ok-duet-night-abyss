from qfluentwidgets import FluentIcon
import time
import cv2
import re

from ok import Logger, TaskDisabledException, Box, find_color_rectangles
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.CommissionsTask import CommissionsTask, QuickMoveTask, Mission

logger = Logger.get_logger(__name__)


class AutoExcavation(DNAOneTimeTask, CommissionsTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.description = "半自动"
        self.default_config.update({
            '轮次': 3,
        })
        self.config_description = {
            '轮次': '打几个轮次',
        }
        self.setup_commission_config()
        self.name = "自动勘察"
        self.action_timeout = 10
        self.progressing = False
        self.quick_move_task = QuickMoveTask(self)
        
    def run(self):
        DNAOneTimeTask.run(self)
        try:
            return self.do_run()
        except TaskDisabledException as e:
            pass
        except Exception as e:
            logger.error('AutoExcavation error', e)
            raise
        self.quick_move_task.stop()

    def do_run(self):
        self.init_param()
        self.load_char()
        _skill_time = 0
        while True:
            if self.in_team():
                self.progressing = self.find_target_health_bar()
                if self.progressing:
                    self.quick_move_task.stop()
                    _skill_time = self.use_skill(_skill_time)
                else:
                    if _skill_time > 0:
                        self.soundBeep(1)
                        _skill_time = 0
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
                self.soundBeep()
                self.wait_until(self.in_team, time_out=30)

            self.sleep(0.2)

    def init_param(self):
        self.current_round = -1
        self.progressing = False
        self.quick_move_task.stop()

    def stop_func(self):
        self.get_round_info()
        if self.current_round >= self.config.get('轮次', 3):
            return True

    def find_target_health_bar(self, threshold: float = 0.5):
        health_bar_box = self.box_of_screen_scaled(2560, 1440, 131, 488, 406, 501, name="health_bar", hcenter=True)
        self.draw_boxes("health_bar", health_bar_box, color="blue")
        min_width = self.width_of_screen(200 / 2560)
        min_height = self.height_of_screen(8 / 1440)
        health_bar = find_color_rectangles(self.frame, green_health_bar_color, min_width, min_height, box=health_bar_box, threshold=0.6)
        self.draw_boxes(boxes=health_bar)
        return health_bar


green_health_bar_color = {
    'r': (140, 145),  # Red range
    'g': (205, 210),  # Green range
    'b': (155, 160)  # Blue range
}
