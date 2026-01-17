import asyncio
import random
import re
import threading
import time

import cv2
from ok import Box, Logger, TaskDisabledException, GenshinInteraction
from qfluentwidgets import FluentIcon
from functools import cached_property

from src.tasks.DNAOneTimeTask import DNAOneTimeTask
from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.CommissionsTask import CommissionsTask

logger = Logger.get_logger(__name__)

setting_menu_selected_color = {
    "r": (220, 255),  # Red range
    "g": (200, 255),  # Green range
    "b": (125, 250),  # Blue range
}

icon_templates = [
    (
        "rouge_yellow_door",
        cv2.imread("assets/rouge/rouge_yellow_door.png", cv2.IMREAD_COLOR),
        {
            "mode": "default",
            "gray_threshold": 0.7,
            "color_threshold": 0.6,
            "score_threshold": 0.6,
        },
    ),
    (
        "rouge_blue_door",
        cv2.imread("assets/rouge/rouge_blue_door.png", cv2.IMREAD_COLOR),
        {
            "mode": "default",
            "gray_threshold": 0.7,
            "color_threshold": 0.6,
            "score_threshold": 0.6,
        },
    ),
    (
        "rouge_target_tag",
        cv2.imread("assets/rouge/rouge_target_tag.png", cv2.IMREAD_COLOR),
        {
            "mode": "vector_red",
            "gray_threshold": 0.6,
            "color_threshold": 0.5,
            "score_threshold": 0.67,
        },
    ),
    (
        "rouge_red_door1",
        cv2.imread("assets/rouge/rouge_red_door1.png", cv2.IMREAD_COLOR),
        {
            "mode": "default",
            "gray_threshold": 0.7,
            "color_threshold": 0.6,
            "score_threshold": 0.67,
        },
    ),
    (
        "rouge_red_door2",
        cv2.imread("assets/rouge/rouge_red_door2.png", cv2.IMREAD_COLOR),
        {
            "mode": "default",
            "gray_threshold": 0.7,
            "color_threshold": 0.6,
            "score_threshold": 0.67,
        },
    ),
    (
        "rouge_red_boos_door",
        cv2.imread("assets/rouge/rouge_red_boos_door.png", cv2.IMREAD_COLOR),
        {
            "mode": "vector_red",
            "score_threshold": 0.5,
        },
    ),
    (
        "rouge_red_boos_door1",
        cv2.imread("assets/rouge/rouge_red_boos_door1.png", cv2.IMREAD_COLOR),
        {
            "mode": "vector_red",
            "score_threshold": 0.5,
        },
    ),
]


class BaseAutoRouge(CommissionsTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._async_loop = None
        self._async_thread = None
        self._ocr_async_lock = asyncio.Lock()
        self._ocr_global_lock = threading.Lock()
        self._pause_events = {
            # 是否暂停检查复活
            "recover": threading.Event(),
            # 是否暂停检查关卡层级
            "level": threading.Event(),
            # 是否暂停检查关卡状态
            "status": threading.Event(),
            # 是否暂停检查卡牌点击
            "click_card": threading.Event(),
        }

        self.current_rogue_type = "战斗"
        self.current_rogue_level = "0/21"
        self.current_rogue_status = "战斗"

        self._monitors = {
            "recover": RecoverMonitor(self, self._pause_events["recover"]),
            "level": RogueLevelMonitor(self, self._pause_events["level"]),
            "status": RogueStatusMonitor(self, self._pause_events["status"]),
            "click_card": CardClickMonitor(self, self._pause_events["click_card"]),
        }
        # 初始全部暂停
        self.post_background(targets=list(self._pause_events.keys()), action="clear")
        self._monitor_futures = {}

    def _ensure_asyncio_loop(self):
        if (
                self._async_loop is None
                or self._async_thread is None
                or not self._async_thread.is_alive()
        ):
            self._async_loop = asyncio.new_event_loop()
            self._async_thread = threading.Thread(
                target=self._async_loop.run_forever, daemon=True
            )
            self._async_thread.start()

    def run(self):
        try:
            self._ensure_asyncio_loop()
            for k, monitor in self._monitors.items():
                f = self._monitor_futures.get(k)
                if not f or f.done() or f.cancelled():
                    self._monitor_futures[k] = asyncio.run_coroutine_threadsafe(
                        monitor.run(), self._async_loop
                    )

        except TaskDisabledException:
            pass
        except Exception as e:
            logger.error("AutoRogueBase error", e)
            raise

    def post_background(self, targets=[], action="clear"):
        # 不处理传入的 targets，仅当为空时默认应用到全部
        keys = list(self._pause_events.keys()) if not targets else [t for t in targets if t in self._pause_events]
        if not keys:
            return
        op = ("clear" if action == "clear" else "set")
        for k in keys:
            ev = self._pause_events.get(k)
            if not ev:
                continue
            if op == "clear":
                ev.clear()
            else:
                ev.set()
        logger.info(f"{'已暂停' if op == 'clear' else '已恢复'}目标={keys}")

    def pause_all_and_get_resumer(self, skip_keys=None):
        """暂停所有指定线程，并返回恢复函数
        Args:
            skip_keys: 需要跳过的键，这些键对应的线程不会被暂停也不会被恢复，保持原样
        """
        if isinstance(skip_keys, str):
            skip = {skip_keys}
        else:
            skip = set(skip_keys or [])

        # 只处理不在 skip 列表中的键
        keys_to_pause = [k for k in self._pause_events.keys() if k not in skip]

        # 记录这些键的原始状态
        prev_states = {k: self._pause_events[k].is_set() for k in keys_to_pause}

        # 只暂停需要暂停的键
        if keys_to_pause:
            self.post_background(targets=keys_to_pause, action="clear")

        def resume():
            """恢复函数：只恢复被暂停的线程，跳过 skip_keys"""
            for k, was_set in prev_states.items():
                ev = self._pause_events.get(k)
                if not ev:
                    continue
                if was_set:
                    ev.set()
                else:
                    ev.clear()
            return True

        return resume

    def _ocr_call_with_retry(self, **kwargs):
        for _ in range(3):
            try:
                return self.ocr(**kwargs)
            except RuntimeError as e:
                if "Infer Request is busy" in str(e):
                    time.sleep(0.05)
                    continue
                raise
        return None

    async def safe_ocr(self, **kwargs):
        async with self._ocr_async_lock:
            def _call():
                with self._ocr_global_lock:
                    return self._ocr_call_with_retry(**kwargs)

            return await asyncio.to_thread(_call)

    def safe_ocr_sync(self, **kwargs):
        with self._ocr_global_lock:
            return self._ocr_call_with_retry(**kwargs)

    async def safe_wait_ocr(self, *, time_out=1.0, settle_time=0.0, interval=0.1, **kwargs):
        deadline = time.time() + float(time_out)
        result = None
        while time.time() < deadline:
            result = await self.safe_ocr(**kwargs)
            if result:
                break
            await asyncio.sleep(interval)
        if result and settle_time and settle_time > 0:
            await asyncio.sleep(settle_time)
            result = await self.safe_ocr(**kwargs)
        return result

    def safe_wait_ocr_sync(self, *, time_out=1.0, settle_time=0.0, interval=0.1, **kwargs):
        deadline = time.time() + float(time_out)
        result = None
        while time.time() < deadline:
            result = self.safe_ocr_sync(**kwargs)
            if result:
                break
            self.sleep(interval)
        if result and settle_time and settle_time > 0:
            self.sleep(settle_time)
            result = self.safe_ocr_sync(**kwargs)
        return result
        return result

    def stop_monitors(self, targets=None):
        keys = list(self._monitors.keys()) if not targets else [t for t in targets if t in self._monitors]
        for k in keys:
            f = self._monitor_futures.get(k)
            if f and not f.done():
                f.cancel()
        return True

    # 肉鸽复位
    def reset_and_transport_rouge(self):
        self.wait_until(self.in_team, time_out=5, settle_time=0.5)
        self.send_key("esc")
        self.sleep(0.5)
        self.click_relative_random(0.688, 0.875, 0.730, 0.95)
        setting_box = self.box_of_screen_scaled(
            2560, 1440, 738, 4, 1123, 79, name="other_section", hcenter=True
        )
        setting_other = self.wait_until(
            lambda: self.find_one("setting_other", box=setting_box),
            time_out=10,
            raise_if_not_found=True,
        )
        self.wait_until(
            condition=lambda: self.calculate_color_percentage(
                setting_menu_selected_color, setting_other
            )
                              > 0.24,
            post_action=lambda: self.click_box_random(setting_other),
            pre_action=lambda: self.sleep(0.5),
            time_out=10,
        )
        confirm_box = self.box_of_screen_scaled(
            2560, 1440, 1298, 776, 1368, 843, name="confirm_btn", hcenter=True
        )
        self.wait_until(
            condition=lambda: self.find_start_btn(box=confirm_box),
            post_action=lambda: self.click_relative_random(
                0.501, 0.294, 0.690, 0.325, use_safe_move=True
            ),
            pre_action=lambda: self.sleep(0.5),
            time_out=10,
        )
        if not self.wait_until(
                condition=self.in_team,
                post_action=lambda: self.click_relative_random(
                    0.514, 0.547, 0.671, 0.578, after_sleep=0.5
                ),
                time_out=10,
        ):
            self.ensure_main()
            return False
        self.sleep(0.6)
        self.send_key("space")
        self.sleep(0.2)
        return True

    @cached_property
    def genshin_interaction(self):
        """
        缓存 Interaction 实例，避免每次鼠标移动都重新创建对象。
        需要确保 self.executor.interaction 和 self.hwnd 在此类初始化时可用。
        """
        # 确保引用的是正确的类
        return GenshinInteraction(self.executor.interaction.capture, self.hwnd)

    def execute_mouse_rotation(self, action):
        direction = action.get("direction", "up")
        angle = action.get("angle", 0)
        sensitivity = action.get("sensitivity", 10)

        pixels = int(angle * sensitivity)

        # 使用字典映射替代 if-elif 链，更简洁
        direction_map = {
            "left": (-pixels, 0),
            "right": (pixels, 0),
            "up": (0, -pixels),
            "down": (0, pixels),
        }

        if direction not in direction_map:
            logger.warning(f"未知的鼠标方向: {direction}")
            return

        dx, dy = direction_map[direction]
        self.execute_mouse_move(dx, dy)
        logger.debug(f"鼠标视角旋转: {direction}, 角度: {angle}, 像素: {pixels}")

    def execute_mouse_move(self, dx, dy):
        """
        优化：复用 genshin_interaction 实例，避免频繁创建对象。
        """
        self.try_bring_to_front()

        # 使用缓存的实例
        self.genshin_interaction.move_mouse_relative(int(dx), int(dy))

    def relative_create_box(self, name, x1, y1, x2, y2):
        """
        创建一个基于当前框的相对位置的新框
        :param box: 当前框
        :param dx: 水平偏移量
        :param dy: 垂直偏移量
        :param w: 新框的宽度
        :param h: 新框的高度
        :return: 新框的字典
        """
        return self.box_of_screen_scaled(
            2560,
            1440,
            2560 * x1,
            1440 * y1,
            2560 * x2,
            1440 * y2,
            name=name,
            hcenter=True,
        )


class RecoverMonitor:
    def __init__(self, owner: BaseAutoRouge, pause_event: threading.Event):
        self.owner = owner
        self.pause_event = pause_event

    async def run(self):
        while (
                self.owner.executor.current_task is not None
                and not self.owner.executor.exit_event.is_set()
        ):
            if not self.pause_event.is_set():
                await asyncio.sleep(0.1)
                continue
            await asyncio.sleep(5)
            box = self.owner.relative_create_box("recover", 0.49, 0.9, 0.52, 0.92)
            text = await self.owner.safe_ocr(box=box, match=re.compile(".*", re.IGNORECASE))
            if text:
                logger.info("检测到复苏按钮，点击")
                self.owner.send_key("x", down_time=3)


class RogueLevelMonitor:
    def __init__(self, owner: BaseAutoRouge, pause_event: threading.Event):
        self.owner = owner
        self.pause_event = pause_event

    async def run(self):
        while (
                self.owner.executor.current_task is not None
                and not self.owner.executor.exit_event.is_set()
        ):
            if not self.pause_event.is_set():
                await asyncio.sleep(0.1)
                continue
            await asyncio.sleep(0.2)
            box = self.owner.relative_create_box("recover", 0.44, 0.01, 0.56, 0.12)
            text = await self.owner.safe_ocr(box=box, match=re.compile(".*", re.IGNORECASE))
            if text:
                num_pattern, text_field = self.identify_fields(text)
                all_level = ['1/21', '2/21', '3/21', '4/21', '5/21', '6/21', '7/21', '8/21', '9/21', '10/21', '11/21',
                             '12/21', '13/21', '14/21', '15/21', '16/21', '17/21', '18/21', '19/21', '20/21', '21/21']
                if num_pattern in all_level and text_field in ['战斗', '奇遇', '休整', '高危战斗']:
                    self.owner.current_rogue_level = num_pattern
                    self.owner.current_rogue_type = text_field
                    self.owner.info_set("当前关卡", self.owner.current_rogue_level)
                    self.owner.info_set("当前关卡类型", self.owner.current_rogue_type)

    def identify_fields(self, box_array):
        """
        智能识别数组中的数字和文本字段
        """
        numbers = None
        text_field = None

        for item in box_array:
            value = item.name
            if "/" in value:
                # 分数格式如 "8/21"
                numbers = value
            else:
                # 其他情况认为是文本
                text_field = value

        return numbers, text_field


class RogueStatusMonitor:
    def __init__(self, owner: BaseAutoRouge, pause_event: threading.Event):
        self.owner = owner
        self.pause_event = pause_event

    async def run(self):
        while (
                self.owner.executor.current_task is not None
                and not self.owner.executor.exit_event.is_set()
        ):
            if not self.pause_event.is_set():
                await asyncio.sleep(0.1)
                continue
            await asyncio.sleep(0.2)
            box2 = self.owner.relative_create_box(
                "current_rogue_type", 0.91, 0.10, 0.99, 0.13
            )
            text2 = await self.owner.safe_ocr(box=box2, match=re.compile(".*", re.IGNORECASE))
            if text2 and text2[0].name in ['战斗', '奇遇', '休整', '高危战斗', '继续探索']:
                self.owner.current_rogue_status = text2[0].name
                self.owner.info_set("当前关卡状态", self.owner.current_rogue_status)


class CardClickMonitor:
    def __init__(self, owner: BaseAutoRouge, pause_event: threading.Event):
        self.owner = owner
        self.pause_event = pause_event

    async def run(self):
        while (
                self.owner.executor.current_task is not None
                and not self.owner.executor.exit_event.is_set()
        ):
            if not self.pause_event.is_set():
                logger.debug("click_card关闭中")
                await asyncio.sleep(0.1)
                continue
            await asyncio.sleep(1)
            boxes = [(0.44, 0.50, 0.56, 0.67)]
            for box_x, box_y, box_x1, box_y1 in boxes:
                box = self.owner.relative_create_box("click_card", box_x, box_y, box_x1, box_y1)
                text = await self.owner.safe_ocr(box=box, match=re.compile(".*", re.IGNORECASE), name="card_text")
                if text and '探索奖励' not in text[0].name:
                    logger.info("检测到卡牌文字需要点击空白关闭，点击")
                    await asyncio.sleep(1)
                    self.owner.click_relative_random(0.16, 0.41, 0.25, 0.56)




class AutoRogueTask(BaseAutoRouge, DNAOneTimeTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动80级 迷津"
        self.description = "全自动80级迷津，只能使用夫人"
        self.group_name = "全自动2"
        self.group_icon = FluentIcon.CAFE

        # 最多执行三轮照门
        self.max_round = 3

        self.setup_commission_config()
        keys_to_remove = [
            "启用自动穿引共鸣",
            "自动选择首个密函和密函奖励",
            "优先选择持有数为0的密函奖励",
            "委托手册指定轮次",
            "委托手册",
            "轮次",
            "使用技能",
            "技能释放频率",
        ]
        for key in keys_to_remove:
            self.default_config.pop(key, None)

        self.action_timeout = 10

    def run(self):
        DNAOneTimeTask.run(self)
        BaseAutoRouge.run(self)
        self.move_mouse_to_safe_position(save_current_pos=False)
        self.set_check_monthly_card()
        try:
            return self.do_run()
        except TaskDisabledException:
            pass
        except Exception as e:
            logger.error("AutoRogueTask error", e)
            raise

    def do_run(self):
        self.init_param()
        self.load_char()
        # 记录当前波次
        _wave = -1
        # 标记是否正在等待下一个波次的到来
        _wait_next_wave = False
        # 用于记录当前波次开始的时间戳
        _wave_start = 0

        # done = self.auto_attack()
        # self.sleep(10)

        # self.auto_dialogue()

        flag=0
        while True:
            flag+=1
            logger.info(f"第{flag}次开始")
            # 启动卡牌点击和管卡信息检测线程
            self.post_background(targets=["recover","level","status","click_card"], action="clear")
            self.post_background(targets=["level","status","click_card"], action="set")
            # 等待3秒，让self.current_rogue_status和self.current_rogue_level赋值稳定
            self.sleep(3)
            # 判断是否起始位置，根据页面文字"坠入深渊"
            if not self.in_team() and self.current_rogue_level == "0/21":
                logger.info("未在肉鸽中，启动肉鸽")
                self.start_rogue()
                # 等待3秒，让self.current_rogue_status和self.current_rogue赋值稳定
                self.sleep(3)
            logger.info(f"开始新一层{self.current_rogue_level}，当前状态为{self.current_rogue_status},当前关卡为{self.current_rogue_type}")
            if self.current_rogue_status != "继续探索":
                if "战斗" in self.current_rogue_type:
                    logger.info(f"当前为战斗关卡")
                    self.sleep(0.3)
                    done = self.auto_attack()
                    if done == "done":
                        self.current_rogue_level = "0/21"
                        continue
                elif self.current_rogue_type == "奇遇":
                    logger.info(f"当前为奇遇关卡")
                    self.auto_serendipity()
                elif self.current_rogue_type == "休整":
                    logger.info(f"当前为休整关卡")
                    self.auto_rest()
            self.sleep(2)
            # 等待回到团队，开始进门
            if self.wait_until(self.in_team, time_out=10):
                self.post_background(targets=["recover","level","status","click_card"], action="clear")
                self.post_background(targets=["level","status"], action="set")
                # 处于探索状态，直接走门
                self.walk_to_target_in()
                self.sleep(3.5)
                logger.info(f"已走至门,进入下个循环")


    def init_param(self):
        self.stop_mission = False
        self.current_round = 0
        self.reset_wave_info()
        self.skill_time = 0

    # 开始肉鸽
    def start_rogue(self):
        if self.in_team():
            return
        if self.safe_wait_ocr_sync(
            box=self.relative_create_box("start1", 0.86, 0.79, 0.96, 0.87),
            match=re.compile("坠入深渊", re.IGNORECASE),
            time_out=20,
        ):
            # 点击坠入深渊
            self.click_relative_random(0.86, 0.79, 0.96, 0.87)
        if self.safe_wait_ocr_sync(
            box=self.relative_create_box("start2", 0.83, 0.87, 0.92, 0.91),
            time_out=1,
            settle_time=0.3,
            match=re.compile(".*探索", re.IGNORECASE),
        ):
            # 点击开始探索
            self.click_relative_random(0.83, 0.87, 0.92, 0.91)
        # 等待进入肉鸽
        self.wait_until(self.in_team, time_out=20)
        logger.info(f"已进入肉鸽")

    # 战斗关卡处理
    def auto_attack(self, has_move=True):
        """
        自动攻击,如果has_move为True,则会移动到目标位置
        """
        # 启动复活检测线程
        self.post_background(targets=["recover","level","status","click_card"], action="clear")
        self.post_background(targets=["recover","click_card"], action="set")
        # 7/14/21是boos
        if self.current_rogue_level in ["7/21","14/21","21/21"]:
            self.auto_attack_boos(has_move)
        else:
            self.auto_attack_minion(has_move)
        if self.current_rogue_level == "21/21":
            self.post_background(targets=["recover", "level", "status", "click_card"], action="clear")
            return "done"
        # 关闭复活检测线程
        self.post_background(targets=["recover","level","status","click_card"], action="clear")
        self.post_background(targets=["status","click_card","level"], action="set")
        return "continue"

    # 打boos
    def auto_attack_boos(self, has_move=True):
        """
        自动攻击boos,如果has_move为True,则会移动到目标位置
        """
        if has_move:
            self.sleep(1)
            self.send_key_down("w")
            self.sleep(0.2)
            self.send_key("lshift")
            self.sleep(2)
            self.send_key("lshift")
            self.sleep(2)
            self.send_key("lshift")
            self.sleep(2)
            self.send_key("lshift")
            self.sleep(2)
            self.middle_click(0.5, 0.5)
            self.sleep(random.uniform(0.48, 0.52))
            self.send_key_up("w")
        now = time.time()
        interval = 12  # 12秒间隔
        self.send_key(self.get_ultimate_key())
        while True:
            cur_time = time.time()
            if (cur_time - now) >= interval:
                now = cur_time
                self.middle_click(0.5, 0.5)
                self.right_click(down_time=0.5)
                self.sleep(0.5)
                self.send_key(self.get_ultimate_key())
                # 随机0.8到1.2秒
                self.sleep(random.uniform(0.7, 0.9))
            # 点击鼠标中键，锁怪
            self.middle_click(0.5, 0.5)
            self.sleep(random.uniform(0.48, 0.52))
            self.send_key(self.get_combat_key())
            self.sleep(random.uniform(0.48, 0.52))
            if self.current_rogue_level == "21/21":
                box2 = self.relative_create_box("current_rogue_status", 0.2, 0.2, 0.8, 0.8)
                text2 = self.safe_ocr_sync(box=box2, match=re.compile("空白", re.IGNORECASE))
                if text2:
                    break
            else:
                box2 = self.relative_create_box("current_rogue_status", 0.91, 0.10, 0.99, 0.13)
                text2 = self.safe_ocr_sync(box=box2, match=re.compile(".*", re.IGNORECASE))
                if text2 and text2[0].name in '继续探索':
                    break
            # 随机按一下wasd
            self.send_key(random.choice(["w", "a", "s", "d"]))

    # 打小怪关卡
    def auto_attack_minion(self, has_move=True):
        """
        自动攻击boos,如果has_move为True,则会移动到目标位置
        """
        if has_move:
            self.send_key_down("w")
            self.sleep(0.2)
            self.send_key("space")
            self.sleep(0.3)
            self.send_key("lshift")
            self.sleep(0.5)
            self.send_key("lshift")
            self.sleep(random.uniform(0.35, 0.45))
            self.send_key_up("w")
            self.sleep(0.1)
            self.send_key("s")
        logger.info("战斗中")
        now = time.time()
        interval = 12  # 12秒间隔
        # 第一次需要放q
        self.send_key(self.get_ultimate_key())
        self.sleep(2.4)
        while True:
            cur_time = time.time()
            logger.info(f"当前时间:{cur_time}，距离上次放q时间:{cur_time - now}")
            if (cur_time - now) >= interval:
                self.sleep(1)
                now = cur_time
                self.send_key(self.get_ultimate_key())
                # 随机2.3到2.5秒
                self.sleep(random.uniform(2.3, 2.5))
                self.send_key("space")
                self.sleep(0.2)
                self.send_key("space")
                self.sleep(0.13)
            self.send_key(self.get_combat_key())
            self.sleep(random.uniform(1.05, 1.15))
            self.execute_mouse_rotation(
                {"direction": "right", "angle": 1, "sensitivity": 600}
            )
            # 战斗结束判断
            box2 = self.relative_create_box("current_rogue_status", 0.91, 0.10, 0.99, 0.13)
            text2 = self.safe_ocr_sync(box=box2, match=re.compile(".*", re.IGNORECASE))

            if  text2 and text2[0].name in '继续探索':
                logger.info("战斗完成")
                break
            # 随机按一下wasd
            self.send_key(random.choice(["w", "a", "s", "d"]))

    # 将号令怪聚集起来，暂时还不能用
    def auto_aggregation(self):
        logger.error("聚合中")
        self.send_key_down("w")
        self.sleep(0.2)
        self.send_key_down("lshift")
        self.sleep(1.5)
        self.send_key_up("w")
        self.send_key_down("a")
        self.sleep(1.4)
        self.send_key_up("a")
        self.send_key_down("d")
        self.sleep(5.4)
        self.send_key_up("d")
        self.send_key_up("lshift")
        # 复位
        self.reset_and_transport_rouge()

    # 休整关卡处理
    def auto_rest(self):
        logger.info(f"休整关卡")
        self.auto_walk_rest_and_serendipity()

    # 奇遇处理
    def auto_serendipity(self):
        self.auto_walk_rest_and_serendipity()
        # 进入奇遇对话
        self.walk_to_target_in()
        self.sleep(3)
        self.auto_dialogue()
    # 对话处理
    def auto_dialogue(self):
        logger.info("奇遇对话处理中")
        self.post_background(["click_card"],'set')
        resume = self.pause_all_and_get_resumer(["click_card"])
        while True:
            stop_text = self.safe_ocr_sync(
                box=self.relative_create_box("current_rogue_type", 0.91, 0.10, 0.99, 0.13),
                match=re.compile(".*", re.IGNORECASE)
            )
            if stop_text and ('继续' in stop_text[0].name or '探索' in stop_text[0].name):
                logger.info(f"停止对话循环")
                break
            logger.info(f"对话循环中")
            content_btn_box = [(0.60, 0.53, 0.87, 0.56),(0.60, 0.65, 0.87, 0.70), (0.60, 0.78, 0.87, 0.83)]
            juxu_box = self.relative_create_box("jixu", 0.96, 0.95, 0.999, 0.999)
            juxu_text = self.safe_ocr_sync(box=juxu_box, match=re.compile(".*", re.IGNORECASE))
            # 检测操继续存在，点击页面
            if juxu_text:
                logger.info(f"识别到继续，点击任意继续")
                self.click_relative_random(0.2,0.4,0.4,0.6)
                self.sleep(0.3)
            else:
                # 暂停1秒，让别得线程可以抢占到safe_ocr
                self.sleep(1)
                text_box = []
                # 拿到全部选项
                for x1, y1, x2, y2 in content_btn_box:
                    text = self.safe_ocr_sync(
                        box=self.relative_create_box("paotai", x1, y1, x2, y2),
                        match=re.compile(".*", re.IGNORECASE),
                    )
                    logger.info(f"奇遇对话识别到的文本:{text_box}")
                    if text:
                        text_box += text
                # 选择并点击选项
                for box in text_box:
                    name = box.name
                    if "炮台轰击" in name:
                        self.click_box_random(box)
                        self.sleep(1)
                        self.send_key_down("a")
                        self.send_key_down("space")
                        self.sleep(0.5)
                        self.send_key_up("space")
                        self.sleep(1)
                        self.send_key_up("a")
                        self.send_key("f")
                        self.sleep(1)
                        self.send_key("esc")
                        self.sleep(1)
                        self.click_relative_random(0.55, 0.55, 0.64, 0.56)
                        self.sleep(1)
                        self.click_relative_random(0.80, 0.55, 0.91, 0.56)
                        self.sleep(1)
                        self.send_key("w", down_time=2)
                        stop = True
                        break

                    is_combat = "战斗" not in name or "战" not in name or "斗" not in name
                    patterns = [r'1000\[余.*', r'750\[余.*', r'获得.*余.*', r'金色\[遗物\]', r'金色\[烛芯\]',
                                r'选取一个\[遗物\]', r'选取一个\[烛芯\]', r"无任何变化", r'随机[紫金]色\[.*',r'随机.*色或.*色\[.*']

                    for pattern in patterns:
                        logger.info(f"比对结果:{re.search(pattern, name)}")
                        if re.search(pattern, name)  and is_combat:
                            logger.info(f"点击{name}")
                            self.click_box_random(box)
                            # 暂停3秒，让别得线程可以抢占到safe_ocr
                            self.sleep(3)
                            break
                # 前方没有选中选项，直接点击非战斗选项
                for box in text_box:
                    name = box.name
                    if "战斗" not in name or "战" not in name or "斗" not in name:
                        logger.info(f"点击{name}")
                        self.click_box_random(box)
                        # 暂停3秒，让别得线程可以抢占到safe_ocr
                        self.sleep(3)
                        break
        resume()

    # 奇遇和休整关卡先向前移动五秒
    def auto_walk_rest_and_serendipity(self):
        self.send_key_down('w')
        self.sleep(5.2)
        self.send_key_up('w')

    # 寻找门或者对话目标
    def fin_door(self):
        # if self.current_rogue_level in ["6/21", "13/21", "20/21"]:
        #     return None, None, 0.0
        frame_bgr = self.frame
        # search_box = self.relative_create_box("search_box", 0.14, 0.17, 0.79, 0.83)
        search_box = self.relative_create_box("search_box", 0.25, 0.17, 0.75, 0.83)
        default_base = [
            "rouge_yellow_door",
            "rouge_blue_door",
            "rouge_red_door1",
            "rouge_red_door2",
        ]
        if self.current_rogue_level in ["6/21", "13/21"]:
            base = ['rouge_red_boos_door']
        elif self.current_rogue_level in ["20/21"]:
            base = ['rouge_red_boos_door1']
        elif self.current_rogue_type == "战斗":
            base = default_base
        elif self.current_rogue_type == "奇遇":
            if self.current_rogue_status == "继续探索":
                base = default_base
            else:
                base = ["rouge_target_tag"]
        elif self.current_rogue_type == "休整":
            base = default_base
        else:
            base = default_base   
        icon_templates_ = [icon for icon in icon_templates if icon[0] in base]
        matched_box, name, score = None, None, 0.0
        logger.info(f"匹配模板:{base}")
        if 'rouge_red_boos_door' in base or 'rouge_red_boos_door1' in base:
            matched_box, name, score = match_icon_special_symbols(
                box=search_box,
                icon_templates=icon_templates_,
                frame_bgr=frame_bgr,
            )
        else:
            matched_box, name, score = match_icon_in_screenshot(
                box=search_box,
                icon_templates=icon_templates_,
                frame_bgr=frame_bgr,
            )
        if matched_box:
            return matched_box, name, score
        return None, None, 0.0


    # 找门
    def find_target(self,has_move=False):
        """
        找进门或者对话目标
        """
        matched_box, name, score = self.fin_door()
        if matched_box is None:
            self.execute_mouse_rotation({"direction": "left","angle": 1,"sensitivity": random.uniform(170, 190)})
            self.sleep(0.8)
            if has_move:
                key = random.choice(["w","a","s","d"])
                self.send_key_down(key)
                self.sleep(random.uniform(0.2, 0.39))
                self.send_key_up(key)
                self.sleep(0.4)
            return None, None, 0.0
        self.draw_boxes(boxes=[matched_box], feature_name=name)
        logger.info(f"找到目标: {name}，分数: {score}, 框: {matched_box}")
        return matched_box, name, score

    # 向目标转移一次人物视角
    def rotate_to_target(self, target_box, name):
        """
        向目标转移一次人物视角
        """
        logger.info(f"目标框: {target_box}")
        screen_width, screen_height = self.frame.shape[1], self.frame.shape[0]
        screen_center_x, screen_center_y = screen_width // 2, screen_height // 2
        icon_templates_ = [icon for icon in icon_templates if icon[0] == name]
        while True:
            center_x = target_box.x + target_box.width // 2
            center_y = target_box.y + target_box.height // 2
            j = abs(center_x - screen_center_x)
            i = abs(center_y - screen_center_y)
            if j > 0.05 * screen_width and i < 0.35 * screen_height:
                self.middle_click(0.5, 0.5)
                if center_x < screen_center_x:
                    self.execute_mouse_rotation(
                        {"direction": "left", "angle": 1, "sensitivity": j / 2}
                    )
                else:
                    self.execute_mouse_rotation(
                        {"direction": "right", "angle": 1, "sensitivity": j / 2}
                    )
                self.sleep(0.4)
                frame_bgr = self.frame
                search_box = self.relative_create_box("search_box", 0.14, 0.17, 0.79, 0.83)
                if 'rouge_red_boos_door' == name or 'rouge_red_boos_door1' == name:
                    matched_box, matched_name, score = match_icon_special_symbols(
                        box=search_box,
                        icon_templates=icon_templates_,
                        frame_bgr=frame_bgr,
                    )
                else:
                    matched_box, matched_name, score = match_icon_in_screenshot(
                        box=search_box,
                        icon_templates=icon_templates_,
                        frame_bgr=frame_bgr,
                    )
                self.sleep(0.4)
                if matched_box is not None:
                    self.draw_boxes(boxes=[matched_box], feature_name=matched_name)
                    logger.info(f"rotate_to_target找到目标: {matched_name}，分数: {score}, 框: {matched_box}")
                    target_box = matched_box
                    name = matched_name
                    continue
                return False
            return True

    # 移动人物到目标，门/奇遇点 并进入
    def walk_to_target_in(self,is_first=True):
        """
        移动人物到目标，门/奇遇点，并进入
        """
        if self.current_rogue_type in ["战斗"] and is_first:
            self.reset_and_transport_rouge()
        flag = 0    
        while True:
            flag += 1
            # 找门/奇遇点，每6次未成功找到，需要移动一次
            door_box, name, _ = self.find_target(has_move=flag > 6)
            if flag > 3:
                flag=0
            if not door_box or not self.rotate_to_target(door_box, name):
                continue
            logger.info(f"已经找到门并转移视角:{door_box}")
            self.sleep(0.5)
            self.send_key_down("w")
            self.sleep(0.2)
            box = self.relative_create_box("door_type", 0.64, 0.47, 0.79, 0.52)
            text = self.safe_wait_ocr_sync(
                box=box,
                match=re.compile(".*", re.IGNORECASE),
                time_out=5,
            )
            forbidden_chars = {"米","独","芯","兑","换","闲","聊","遗","物","获","取","补","给"}
            if text and all(char not in text[0].name for char in forbidden_chars):
                self.send_key("f")
                self.send_key_up("w")
                return True







import cv2
import numpy as np
from typing import Sequence, Tuple, Optional, Iterable, Any, Dict

def _ensure_bgr(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image


def _compute_hist_similarity(template_hsv: np.ndarray, patch_hsv: np.ndarray) -> float:
    h_bins = 32
    s_bins = 32
    v_bins = 32
    hist_template_h = cv2.calcHist([template_hsv], [0], None, [h_bins], [0, 180])
    hist_template_s = cv2.calcHist([template_hsv], [1], None, [s_bins], [0, 256])
    hist_template_v = cv2.calcHist([template_hsv], [2], None, [v_bins], [0, 256])
    hist_patch_h = cv2.calcHist([patch_hsv], [0], None, [h_bins], [0, 180])
    hist_patch_s = cv2.calcHist([patch_hsv], [1], None, [s_bins], [0, 256])
    hist_patch_v = cv2.calcHist([patch_hsv], [2], None, [v_bins], [0, 256])
    cv2.normalize(hist_template_h, hist_template_h)
    cv2.normalize(hist_template_s, hist_template_s)
    cv2.normalize(hist_template_v, hist_template_v)
    cv2.normalize(hist_patch_h, hist_patch_h)
    cv2.normalize(hist_patch_s, hist_patch_s)
    cv2.normalize(hist_patch_v, hist_patch_v)
    score_h = cv2.compareHist(hist_template_h, hist_patch_h, cv2.HISTCMP_CORREL)
    score_s = cv2.compareHist(hist_template_s, hist_patch_s, cv2.HISTCMP_CORREL)
    score_v = cv2.compareHist(hist_template_v, hist_patch_v, cv2.HISTCMP_CORREL)
    score = float((score_h + score_s + score_v) / 3.0)
    return max(0.0, min(1.0, score))


def _compute_edge_similarity(template_gray: np.ndarray, patch_gray: np.ndarray) -> float:
    template_edges = cv2.Canny(template_gray, 50, 150)
    patch_edges = cv2.Canny(patch_gray, 50, 150)
    result = cv2.matchTemplate(patch_edges, template_edges, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val)


def _create_box(x: int, y: int, w: int, h: int, name: Optional[str]) -> Box:
    try:
        return Box(x=x, y=y, width=w, height=h, name=name)
    except TypeError:
        try:
            return Box(x, y, w, h, name)
        except TypeError:
            return Box(x, y, w, h)


def _normalize_templates(
    icon_templates: Sequence[Tuple[str, np.ndarray, Dict[str, Any]]]
) -> Iterable[Tuple[str, np.ndarray, Dict[str, Any]]]:
    for name, template, params in icon_templates:
        if params is None:
            params = {}
        yield str(name), template, dict(params)


def _create_red_mask_from_hsv(hsv: np.ndarray) -> np.ndarray:
    lower1 = np.array([0, 80, 80], dtype=np.uint8)
    upper1 = np.array([10, 255, 255], dtype=np.uint8)
    lower2 = np.array([170, 80, 80], dtype=np.uint8)
    upper2 = np.array([180, 255, 255], dtype=np.uint8)
    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(mask1, mask2)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return mask


def match_icon_in_screenshot(
    box: Box,
    icon_templates: Sequence[Tuple[str, np.ndarray, Dict[str, Any]]],
    frame_bgr: np.ndarray,
    scales: Sequence[float] = (0.8, 0.9, 1.0, 1.1, 1.2),
    max_candidates_per_scale: int = 5,
) -> Tuple[Optional[Box], Optional[str], float]:
    if not icon_templates:
        return None, None, 0.0
    templates_seq = list(_normalize_templates(icon_templates))
    if not templates_seq:
        return None, None, 0.0
    frame_bgr = _ensure_bgr(frame_bgr)
    screenshot_bgr = box.crop_frame(frame_bgr)
    if screenshot_bgr is None or screenshot_bgr.size == 0:
        return None, None, 0.0
    screenshot_bgr = _ensure_bgr(screenshot_bgr)
    screenshot_gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
    screenshot_hsv = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2HSV)
    screenshot_red_mask = None
    logger.debug(
        f"图标匹配开始 模板数量={len(templates_seq)} "
        f"截图尺寸={tuple(screenshot_bgr.shape)} "
        f"缩放比例={tuple(scales)} "
    )
    for index, (name, template, params) in enumerate(templates_seq):
        template_mode = str(params.get("mode", "default"))
        template_gray_threshold = float(params.get("gray_threshold", 0.7))
        template_color_threshold = float(params.get("color_threshold", 0.6))
        logger.debug(
            f"开始匹配模板 序号={index} 名称={name} "
            f"模式={template_mode} 灰度阈值={template_gray_threshold} 颜色阈值={template_color_threshold}"
        )
        template_bgr = _ensure_bgr(template)
        template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        template_hsv = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2HSV)
        th, tw = template_gray.shape[:2]
        best_box_for_template: Optional[Box] = None
        best_score_for_template: float = 0.0
        if template_mode == "vector_red":
            effective_gray_threshold = template_gray_threshold * 0.8
            use_color_gate = False
            template_red_mask = _create_red_mask_from_hsv(template_hsv)
            if screenshot_red_mask is None:
                screenshot_red_mask = _create_red_mask_from_hsv(screenshot_hsv)
        else:
            effective_gray_threshold = template_gray_threshold
            use_color_gate = True
            template_red_mask = None
        for scale in scales:
            if scale <= 0:
                continue
            scaled_tw = int(tw * scale)
            scaled_th = int(th * scale)
            if scaled_tw < 4 or scaled_th < 4:
                continue
            if scaled_tw > screenshot_gray.shape[1] or scaled_th > screenshot_gray.shape[0]:
                continue
            scaled_template_gray = cv2.resize(
                template_gray, (scaled_tw, scaled_th), interpolation=cv2.INTER_LINEAR
            )
            scaled_template_hsv = cv2.resize(
                template_hsv, (scaled_tw, scaled_th), interpolation=cv2.INTER_LINEAR
            )
            result = cv2.matchTemplate(screenshot_gray, scaled_template_gray, cv2.TM_CCOEFF_NORMED)
            flat_red = None
            if template_mode == "vector_red":
                scaled_template_red_mask = cv2.resize(
                    template_red_mask,
                    (scaled_tw, scaled_th),
                    interpolation=cv2.INTER_NEAREST,
                )
                result_red = cv2.matchTemplate(
                    screenshot_red_mask, scaled_template_red_mask, cv2.TM_CCOEFF_NORMED
                )
            else:
                result_red = None
            if result.size == 0:
                continue
            flat = result.ravel()
            if result_red is not None:
                flat_red = result_red.ravel()
            if max_candidates_per_scale <= 0:
                if flat_red is not None:
                    combined_flat = flat + flat_red
                    indices = np.argmax(combined_flat)[None]
                else:
                    indices = np.argmax(flat)[None]
            else:
                k = min(max_candidates_per_scale, flat.size)
                if flat_red is not None:
                    combined_flat = flat + flat_red
                    indices = np.argpartition(combined_flat, -k)[-k:]
                else:
                    indices = np.argpartition(flat, -k)[-k:]
            for idx in indices:
                similarity_gray = float(flat[idx])
                if similarity_gray < effective_gray_threshold:
                    continue
                y = int(idx // result.shape[1])
                x = int(idx % result.shape[1])
                global_x = box.x + x
                global_y = box.y + y
                y2 = y + scaled_th
                x2 = x + scaled_tw
                if y2 > screenshot_bgr.shape[0] or x2 > screenshot_bgr.shape[1]:
                    continue
                patch_bgr = screenshot_bgr[y:y2, x:x2]
                patch_gray = screenshot_gray[y:y2, x:x2]
                patch_hsv = screenshot_hsv[y:y2, x:x2]
                color_score = _compute_hist_similarity(scaled_template_hsv, patch_hsv)
                if use_color_gate and color_score < template_color_threshold:
                    continue
                edge_score = _compute_edge_similarity(scaled_template_gray, patch_gray)
                if template_mode == "vector_red":
                    mask_score = float(flat_red[idx])
                    combined_score = (
                        0.15 * similarity_gray
                        + 0.15 * color_score
                        + 0.35 * edge_score
                        + 0.35 * mask_score
                    )
                else:
                    combined_score = (
                        0.5 * similarity_gray + 0.3 * color_score + 0.2 * edge_score
                    )
                if combined_score > best_score_for_template:
                    if template_mode == "vector_red":
                        logger.debug(
                            f"候选更新 模板={name} 综合得分={combined_score:.4f} "
                            f"灰度={similarity_gray:.4f} 颜色={color_score:.4f} 边缘={edge_score:.4f} "
                            f"红色掩码={mask_score:.4f} "
                            f"x={global_x} y={global_y} w={scaled_tw} h={scaled_th}"
                        )
                    else:
                        logger.debug(
                            f"候选更新 模板={name} 综合得分={combined_score:.4f} "
                            f"灰度={similarity_gray:.4f} 颜色={color_score:.4f} 边缘={edge_score:.4f} "
                            f"x={global_x} y={global_y} w={scaled_tw} h={scaled_th}"
                        )
                    best_score_for_template = combined_score
                    best_box_for_template = _create_box(global_x, global_y, scaled_tw, scaled_th, name)
        if best_box_for_template is not None:
            template_score_threshold = float(params.get("score_threshold", 0.67))
            if best_score_for_template < template_score_threshold:
                logger.debug(
                    f"模板匹配得分低于阈值 名称={name} 最佳得分={best_score_for_template:.4f} "
                    f"阈值={template_score_threshold:.2f}"
                )
                continue
            logger.debug(
                f"模板匹配成功 名称={name} 最佳得分={best_score_for_template:.4f} "
                f"位置={best_box_for_template}"
            )
            return best_box_for_template, name, best_score_for_template
        logger.debug(f"模板未匹配到 名称={name}")
    return None, None, 0.0

# 使用的颜色匹配，匹配颜色最接近的色块
def match_icon_special_symbols(
    box: Box,
    icon_templates: Sequence[Tuple[str, np.ndarray, Dict[str, Any]]],
    frame_bgr: np.ndarray,
    scales: Sequence[float] = (0.8, 0.9, 1.0, 1.1, 1.2),
    max_candidates_per_scale: int = 8,
) -> Tuple[Optional[Box], Optional[str], float]:
    if not icon_templates:
        return None, None, 0.0
    templates_seq = list(_normalize_templates(icon_templates))
    if not templates_seq:
        return None, None, 0.0
    frame_bgr = _ensure_bgr(frame_bgr)
    screenshot_bgr = box.crop_frame(frame_bgr)
    if screenshot_bgr is None or screenshot_bgr.size == 0:
        return None, None, 0.0
    screenshot_bgr = _ensure_bgr(screenshot_bgr)
    screenshot_hsv = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2HSV)
    h_map, s_map, v_map = cv2.split(screenshot_hsv)
    best_box: Optional[Box] = None
    best_name: Optional[str] = None
    best_score: float = 0.0
    for name, template, params in templates_seq:
        template_bgr = _ensure_bgr(template)
        template_hsv = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2HSV)
        th, tw = template_hsv.shape[:2]
        if th < 3 or tw < 3:
            continue
        for scale in scales:
            if scale <= 0:
                continue
            w = int(max(3, round(tw * scale)))
            h = int(max(3, round(th * scale)))
            if w > screenshot_hsv.shape[1] or h > screenshot_hsv.shape[0]:
                continue
            tpl_h_mean = float(np.mean(template_hsv[:, :, 0]))
            tpl_s_mean = float(np.mean(template_hsv[:, :, 1]))
            tpl_v_mean = float(np.mean(template_hsv[:, :, 2]))
            mean_h = cv2.blur(h_map, (w, h))
            mean_s = cv2.blur(s_map, (w, h))
            mean_v = cv2.blur(v_map, (w, h))
            dh_raw = np.abs(mean_h.astype(np.float32) - tpl_h_mean)
            dh = np.minimum(dh_raw, 180.0 - dh_raw) / 90.0
            ds = np.abs(mean_s.astype(np.float32) - tpl_s_mean) / 255.0
            dv = np.abs(mean_v.astype(np.float32) - tpl_v_mean) / 255.0
            dist = np.sqrt(dh * dh + ds * ds + dv * dv)
            score_map = 1.0 - np.clip(dist, 0.0, 1.0)
            cx_min = h // 2
            cy_min = w // 2
            cx_max = screenshot_hsv.shape[0] - (h - h // 2)
            cy_max = screenshot_hsv.shape[1] - (w - w // 2)
            valid = score_map[cx_min:cx_max, cy_min:cy_max]
            if valid.size == 0:
                continue
            idx = np.unravel_index(np.argmax(valid), valid.shape)
            cx = idx[0] + cx_min
            cy = idx[1] + cy_min
            x0 = int(np.clip(cy - w // 2, 0, screenshot_hsv.shape[1] - w))
            y0 = int(np.clip(cx - h // 2, 0, screenshot_hsv.shape[0] - h))
            x1 = x0 + w
            y1 = y0 + h
            score = float(valid[idx])
            threshold = float(params.get("score_threshold", 0.6))
            if score >= threshold and score > best_score:
                best_score = score
                best_box = _create_box(box.x + x0, box.y + y0, w, h, name)
                best_name = name
    if best_box is None or best_name is None:
        return None, None, 0.0
    return best_box, best_name, best_score
