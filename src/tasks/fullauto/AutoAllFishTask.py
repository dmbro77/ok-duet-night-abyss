from qfluentwidgets import FluentIcon
import time
import cv2
import numpy as np
import re

from ok import Logger, TaskDisabledException
from src.tasks.fullauto.AutoFishTask import AutoFishTask
from src.tasks.DNAOneTimeTask import DNAOneTimeTask

logger = Logger.get_logger(__name__)


class AutoAllFishTask(AutoFishTask):
    """AutoFishTask
    无悠闲全自动钓鱼
    """
    BAR_MIN_AREA = 1200
    ICON_MIN_AREA = 70
    ICON_MAX_AREA = 400
    CONTROL_ZONE_RATIO = 0.25

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动钓鱼一条龙"
        self.description = "基于自动钓鱼，进一步实现一条龙服务 (原作者: B站无敌大蜜瓜)"
        self.group_name = "全自动"
        self.group_icon = FluentIcon.CAFE

        self.fish_points = [
            {"name": "净界岛", "point": (0.141, 0.001, 0.181, 0.05), "walk": [{"key": 'w', "time": 1.6}]},
            {"name": "冰湖", "point": (0.191, 0.001, 0.221, 0.05),
             "walk": [{"key": 'a', "time": 0.3}, {"key": 'w', "time": 1.6}]},
            {"name": "下水道", "point": (0.241, 0.001, 0.261, 0.05), "walk": []},
            {"name": "浮星埠", "point": (0.281, 0.001, 0.301, 0.05),
             "walk": [{"key": 'w', "time": 0.3}, {"key": 'a', "time": 0.3}]},
            {"name": "百年春", "point": (0.321, 0.001, 0.341, 0.05), "walk": [{"key": 'w', "time": 1.3}]},
            {"name": "潮声岩穴", "point": (0.371, 0.001, 0.381, 0.05),
             "walk": [{"key": 'a', "time": 0.3}, {"key": 'w', "time": 1.2}, {"key": '', "time": 1}]},
            {"name": "枯荣阁", "point": (0.405, 0.001, 0.431, 0.05),
             "walk": [{"key": 'd', "time": 0.3}, {"key": 'w', "time": 0.7}]},
            {"name": "微茫市", "point": (0.451, 0.001, 0.471, 0.05),
             "walk": [{"key": 'a', "time": 0.2}, {"key": 'w', "time": 0.2}]}
        ]
        self.default_config.update({
            '钓鱼点选择': ["净界岛", "冰湖", "下水道", '浮星埠', '百年春', '潮声岩穴', '枯荣阁', '微茫市'],
            "MAX_ROUNDS": 100,
            '自动出售':True,
        })
        self.config_description.update({
            # '钓鱼点选择':"未勾选的钓鱼点不会进行钓鱼",
            "MAX_ROUNDS": "单个钓鱼点最大轮数，鱼塘每天上限为100次",
        })

        # 设置地图选择为下拉选择
        self.config_type["钓鱼点选择"] = {
            "type": "multi_selection",
            "options": ["净界岛", "冰湖", "下水道", '浮星埠', '百年春', '潮声岩穴', '枯荣阁', '微茫市'],
        }

    def run(self):
        # DNAOneTimeTask.run(self)
        try:
            return self.do_run_all()
        except TaskDisabledException:
            pass
        except Exception as e:
            logger.error("AutoFishTask error", e)
            raise

    # 打开到鱼类图鉴页面
    def go_fish(self):
        try:
            if not self.in_team():
                raise Exception("请在大世界开始")
            self.send_key("b")
            self.sleep(0.4)
            self.click_relative_random(0.29, 0.001, 0.33, 0.04)
            self.sleep(0.4)
            # x_step,y_step = 0.06,0.37
            start_x, start_y = 0.09, 0.23
            now = time.time()
            self.click_relative_random(start_x, start_y, start_x + 0.01, start_y + 0.01)
            self.sleep(0.4)
            box1 = self.wait_ocr(
                box=self.box_of_screen_scaled(2560, 1440, 2560 * 0.78, 1440 * 0.80, 2560 * 0.87, 1440 * 0.83,
                                              name="start", hcenter=True),
                match='打开鱼类图鉴',
                time_out=5,
                raise_if_not_found=True,
            )
            box = self.box_of_screen_scaled(2560, 1440, 0.001, 0.001, 0.999, 0.999, name="letter_drag_area",
                                            hcenter=True)
            self.click_box_random(box1[0], use_safe_move=True, safe_move_box=box, down_time=0.02, after_sleep=0.1)
        except Exception as e:
            self.log_error(f"打开鱼类图鉴失败 {e}")
            raise e

            # 切换钓鱼点

    def switch_fish_point(self,current_fish):
        try:
            box = self.box_of_screen_scaled(
                2560, 1440, 0.001, 0.001, 0.999, 0.999,
                name="letter_drag_area", hcenter=True
            )
            self.sleep(0.4)
            self.click_relative_random(
                *current_fish['point'],
                use_safe_move=True, safe_move_box=box, down_time=0.05, after_sleep=0.5
            )
            # self.sleep(0.4)
            # box1 = self.wait_ocr(
            #     box=self.box_of_screen_scaled(2560, 1440, 2560 * 0.80, 1440 * 0.831, 2560 * 0.901, 1440 * 0.871,
            #                                   name="追踪当前钓鱼点", hcenter=True),
            #     match='追踪当前钓鱼点',
            #     time_out=5,
            #     raise_if_not_found=True,
            # )
            # self.sleep(0.4)
            # self.click_box_random(box1[0], use_safe_move=True, safe_move_box=box, down_time=0.02, after_sleep=0.5)
            self.click_relative_random(
                0.80, 0.831, 0.901, 0.871,
                use_safe_move=True, safe_move_box=box, down_time=0.05, after_sleep=0.8
            )
            # box2 = self.wait_ocr(
            #     box=self.box_of_screen_scaled(2560, 1440, 2560 * 0.828, 1440 * 0.841, 2560 * 0.881, 1440 * 0.871,
            #                                   name="传送", hcenter=True),
            #     match='传送',
            #     time_out=5,
            #     raise_if_not_found=True,
            # )
            # self.sleep(0.4)
            # self.click_box_random(box2[0], use_safe_move=True, safe_move_box=box, down_time=0.02, after_sleep=0.4)
            self.click_relative_random(
                0.828, 0.841, 0.881, 0.871,
                use_safe_move=True, safe_move_box=box, down_time=0.02, after_sleep=0.8
            )
            self.sleep(2)
            # 传送地图,等待传送完成
            self.wait_until(self.in_team, time_out=30.0, raise_if_not_found=True, settle_time=1.2)
            # 获取移动方式并执行移动
            walk_step = current_fish['walk']
            for step in walk_step:
                key = step["key"]
                if key:
                    self.send_key_down(key)
                self.sleep(step["time"])
                if key:
                    self.send_key_up(key)
                self.sleep(0.2)
            self.send_key("f")
        except Exception as e:
            self.log_error(f"切换钓鱼点失败 {e}")
            raise e

    # 开始钓鱼

    def start_fish(self):
        try:
            self.sleep(0.5)
            self.wait_click_ocr(
                box=self.box_of_screen_scaled(
                    2560, 1440, 2560 * 0.881, 1440 * 0.871, 2560 * 0.941, 1440 * 0.901,
                    name="start_fish", hcenter=True
                ),
                match=re.compile('开始钓鱼', re.IGNORECASE),
                time_out=20,
                raise_if_not_found=True,
                after_sleep=0.5
            )
        except Exception as e:
            self.log_error(f"开始钓鱼失败 {e}")
            raise e

            # main run

    def do_run_all(self):
        self.go_fish()

        for current_fish in self.fish_points:
            if current_fish['name'] not in self.config.get("钓鱼点选择"):
                continue
            self.switch_fish_point(current_fish)
            self.info_set('当前钓鱼点', f" {current_fish['name']}")
            self.start_fish()
            # self.do_run()
            # 退出钓鱼
            self.sleep(1.5)
            self.send_key('esc')
            self.sleep(1.5)
            self.click_relative_random(0.06, 0.86, 0.07, 0.89, after_sleep=0.8)

        self.fishing_end()

    def fishing_end(self):
        self.send_key("esc")
        if self.config.get('自动出售'):
            # 打开背包
            self.click_relative_random(0.025, 0.86, 0.04, 0.89, after_sleep=0.8)
            # 点击出售
            self.click_relative_random(0.62, 0.80, 0.68, 0.82, after_sleep=0.8)
            # 5中类型鱼类全部勾选
            for point in [
                (0.11, 0.67, 0.12, 0.68),
                (0.14, 0.67, 0.15, 0.68),
                (0.16, 0.67, 0.17, 0.68),
                (0.18, 0.67, 0.19, 0.68),
                (0.21, 0.67, 0.22, 0.68),
            ]:
                self.click_relative_random(*point, after_sleep=0.8)
            # 点击全部出售
            self.click_relative_random(0.83, 0.89, 0.94, 0.91, after_sleep=0.8)