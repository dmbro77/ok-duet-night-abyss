from qfluentwidgets import FluentIcon
import time
import cv2
import re

from ok import Logger, TaskDisabledException, Box, find_color_rectangles, color_range_to_bound
from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.CommissionsTask import CommissionsTask, QuickMoveTask, Mission

logger = Logger.get_logger(__name__)

DEFAULT_ACTION_TIMEOUT = 10


class AutoExcavation(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动勘察"
        self.description = "半自动"
        self.group_name = "半自动"
        self.group_icon = FluentIcon.VIEW

        self.default_config.update({
            '轮次': 3,
        })

        self.setup_commission_config()
        keys_to_remove = ["超时时间"]
        for key in keys_to_remove:
            self.default_config.pop(key, None)

        self.config_description.update({
            "轮次": "打几个轮次",
        })

        self.action_timeout = DEFAULT_ACTION_TIMEOUT
        self.quick_move_task = QuickMoveTask(self)
        self.jiggle_tick = self.create_jiggle_ticker(10)
        self.skill_tick = self.create_skill_ticker()

    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position(save_current_pos=False)
        self.set_check_monthly_card()
        try:
            return self.do_run()
        except TaskDisabledException as e:
            pass
        except Exception as e:
            logger.error("AutoExcavation error", e)
            raise

    def do_run(self):
        self.init_all()
        self.load_char()

        while True:
            if self.in_team():
                self.handle_in_mission()

            _status = self.handle_mission_interface(stop_func=self.stop_func)
            if _status == Mission.START:
                self.wait_until(self.in_team, time_out=DEFAULT_ACTION_TIMEOUT)
                self.sleep(2)
                self.init_all()
                self.handle_mission_start()
            elif _status == Mission.STOP:
                self.log_info("任务中止")
                self.quit_mission()
            elif _status == Mission.CONTINUE:
                self.log_info("任务继续")
                self.init_for_next_round()
                self.wait_until(self.in_team, time_out=DEFAULT_ACTION_TIMEOUT)

                self.sleep(2)
                if not self.find_target_health_bar():
                    self.soundBeep(1)
                
            self.sleep(0.1)

    def init_all(self):
        self.init_for_next_round()
        self.current_round = -1
        self.jiggle_tick.start_next_tick()

    def init_for_next_round(self):
        self.init_runtime_state()
        self.excavator_count = 0

    def init_runtime_state(self):
        self.runtime_state = {"start_time": 0}
        self.skill_tick.reset()

    def handle_in_mission(self):
        if self.find_target_health_bar():
            if self.runtime_state["start_time"] == 0:
                self.runtime_state["start_time"] = time.time()
                self.quick_move_task.reset()
            self.jiggle_tick()
            self.skill_tick()
        else:
            if self.runtime_state["start_time"] > 0:
                self.init_runtime_state()
                self.excavator_count += 1
                if self.excavator_count < 3:
                    self.soundBeep(1)
            self.quick_move_task.run()

    def handle_mission_start(self):
        self.log_info_notify("任务开始")
        self.soundBeep()

    def stop_func(self):
        self.get_round_info()
        if self.current_round >= self.config.get("轮次", 3):
            return True

    def find_target_health_bar(self, threshold: float = 0.6):
        health_bar_box = self.box_of_screen_scaled(2560, 1440, 131, 488, 406, 501, name="health_bar", hcenter=True)
        self.draw_boxes("health_bar", health_bar_box, color="blue")
        min_width = self.width_of_screen(200 / 2560)
        min_height = self.height_of_screen(8 / 1440)
        health_bar = find_color_rectangles(self.frame, green_health_bar_color, min_width, min_height,
                                           box=health_bar_box, threshold=threshold)
        self.draw_boxes(boxes=health_bar)
        return health_bar


green_health_bar_color = {
    "r": (135, 150),  # Red range
    "g": (200, 215),  # Green range
    "b": (150, 165),  # Blue range
}
