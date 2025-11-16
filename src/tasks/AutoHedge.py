from qfluentwidgets import FluentIcon
import time
import re
import cv2
from concurrent.futures import ThreadPoolExecutor

from ok import Logger, TaskDisabledException
from src.tasks.CommissionsTask import CommissionsTask, QuickMoveTask, Mission, _default_movement
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.DNAOneTimeTask import DNAOneTimeTask

logger = Logger.get_logger(__name__)

DEFAULT_ACTION_TIMEOUT = 10


class AutoHedge(DNAOneTimeTask, CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动避险"
        self.description = "半自动"
        self.group_name = "半自动"
        self.group_icon = FluentIcon.VIEW

        # self.default_config.update({
        #     '轮次': 3,
        # })

        self.setup_commission_config()

        self.config_description.update({
            '超时时间': '超时后将发出提示',
        })

        self.action_timeout = DEFAULT_ACTION_TIMEOUT
        self.quick_move_task = QuickMoveTask(self)
        self.external_movement = _default_movement
        self.external_movement_evac = _default_movement
        self._external_config = None
        self._merged_config_cache = None
        self.jiggle_tick = self.create_jiggle_ticker(10)
        self.skill_tick = self.create_skill_ticker()

        self.track_point_pos = 0
        self.mission_complete = False
        self.ocr_executor = None
        self.ocr_future = None
        self.last_ocr_result = -1

    @property
    def config(self):
        if self.external_movement == _default_movement:
            return super().config
        else:
            if self._merged_config_cache is None:
                self._merged_config_cache = super().config.copy()
            self._merged_config_cache.update(self._external_config)
            return self._merged_config_cache

    def config_external_movement(self, approach: callable, evacuation: callable, config: dict):
        if callable(approach) and callable(evacuation):
            self.external_movement = approach
            self.external_movement_evac = evacuation
        else:
            self.external_movement = _default_movement
            self.external_movement_evac = _default_movement
        self._merged_config_cache = None
        self._external_config = config

    def run(self):
        DNAOneTimeTask.run(self)
        self.move_mouse_to_safe_position(save_current_pos=False)
        self.set_check_monthly_card()
        try:
            return self.do_run()
        except TaskDisabledException:
            pass
        except Exception as e:
            logger.error("AutoExploration error", e)
            raise

    def do_run(self):
        self.init_all()
        self.load_char()

        if self.external_movement is not _default_movement and self.in_team():
            self.open_in_mission_menu()

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
                pass
            elif _status == Mission.CONTINUE:
                pass

            self.sleep(0.1)        

    def init_all(self):
        self.init_for_next_round()
        self.jiggle_tick.start_next_tick()
        self.current_round = -1
        self.track_point_pos = 0
        self.mission_complete = False
        if self.ocr_executor is not None:
            self.ocr_executor.shutdown(wait=False, cancel_futures=True)
        self.ocr_executor = ThreadPoolExecutor(max_workers=2)
        self.ocr_future = None
        self.last_ocr_result = -1

    def init_for_next_round(self):
        self.init_runtime_state()

    def init_runtime_state(self):
        self.runtime_state = {"start_time": 0, "in_progress": False, "wait_next_round": False}
        self.skill_tick.reset()

    def handle_in_mission(self):
        self.update_mission_status()
        if self.runtime_state["in_progress"]:
            if self.runtime_state["start_time"] == 0:
                self.runtime_state["start_time"] = time.time()
                self.quick_move_task.reset()
            
            if not self.runtime_state["wait_next_round"] and time.time() - self.runtime_state["start_time"] >= self.config.get("超时时间", 120):
                if self.external_movement is not _default_movement:
                    self.log_info("任务超时")
                    self.open_in_mission_menu()
                    return
                else:
                    self.log_info_notify("任务超时")
                    self.soundBeep()
                    self.runtime_state["wait_next_round"] = True

            self.jiggle_tick()
            if not self.runtime_state["wait_next_round"]:
                self.skill_tick()
        else:
            if self.runtime_state["start_time"] > 0:
                self.init_runtime_state()
                if self.external_movement_evac is not _default_movement:
                    self.log_info("任务结束")
                    self.external_movement_evac()
                    self.log_info(f"外部移动执行完毕。")
                    self.wait_until(lambda: not self.in_team(), time_out=30)
                    return
                else:
                    self.log_info_notify("任务结束")
                    self.soundBeep()
            self.quick_move_task.run()
    
    def handle_mission_start(self):
        if self.external_movement is not _default_movement:
            self.log_info("任务开始")
            self.external_movement()
            self.log_info(f"外部移动执行完毕，等待战斗开始，{DEFAULT_ACTION_TIMEOUT}秒后超时")
            if not self.wait_until(self.runtime_state["in_progress"], post_action=self.update_mission_status, time_out=DEFAULT_ACTION_TIMEOUT):
                self.log_info("超时重开")
                self.open_in_mission_menu()
                return
            else:
                self.log_info("战斗开始")
        else:
            self.log_info_notify("任务开始")
            self.soundBeep()

    def stop_func(self):
        pass

    def update_mission_status(self):
        if self.mission_complete:
            return
        percentage = self.get_serum_process_info()
        if percentage == 100:
            self.runtime_state["in_progress"] = False
            self.mission_complete = True
        elif percentage > 0:
            self.runtime_state["in_progress"] = True
        if not self.runtime_state["in_progress"] and not self.mission_complete:
            _track_point = self.find_top_right_track_pos()
            if _track_point < 0:
                return
            if self.track_point_pos == 0:
                self.track_point_pos = _track_point
            elif (rpd := abs(_track_point - self.track_point_pos) / self.track_point_pos) > 0.02:
                self.log_debug(f"track point diff pct {rpd}")
                self.runtime_state["in_progress"] = True

    def get_serum_process_info(self):
        if self.ocr_future and self.ocr_future.done():
            try:
                texts = self.ocr_future.result()
                if texts and "%" in texts[0].name:
                    name = texts[0].name.replace("%", "")
                    if name.isdigit():
                        pct = int(name)
                        if pct > self.last_ocr_result and pct <= 100:
                            self.last_ocr_result = pct
                            # self.info_set("进度", f"{pct}%")
            except Exception as e:
                logger.error(f"OCR任务出错: {e}")
            finally:
                self.ocr_future = None
        if self.ocr_future is None:
            box = self.box_of_screen_scaled(2560, 1440, 115, 399, 217, 461, name="process_info", hcenter=True)
            self.ocr_future = self.ocr_executor.submit(self.ocr, box=box, match=re.compile(r"\d+%"))
        return self.last_ocr_result

    def find_top_right_track_pos(self):
        box = self.box_of_screen_scaled(2560, 1440, 2183, 82, 2414, 140, name="track_point", hcenter=True)
        template = cv2.resize(self.get_feature_by_name("track_point").mat, None, fx=0.79, fy=0.79,
                              interpolation=cv2.INTER_LINEAR)
        ret = -1
        box = self.find_track_point(box=box, template=template, filter_track_color=True)
        if box is not None:
            ret = box.x
        return ret
