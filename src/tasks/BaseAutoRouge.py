import asyncio
import re
import threading
import time

from functools import cached_property
from ok import Logger, TaskDisabledException, GenshinInteraction


from src.tasks.BaseCombatTask import BaseCombatTask
from src.tasks.CommissionsTask import CommissionsTask


logger = Logger.get_logger(__name__)

setting_menu_selected_color = {
    "r": (220, 255),  # Red range
    "g": (200, 255),  # Green range
    "b": (125, 250),  # Blue range
}

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
        self.current_rogue_level =  "0/21"
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
        logger.info(f"{'已暂停' if op=='clear' else '已恢复'}目标={keys}")

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
        self.wait_until(self.in_team, time_out=5,settle_time=0.5)
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
                all_level = ['1/21', '2/21', '3/21', '4/21', '5/21', '6/21', '7/21', '8/21', '9/21', '10/21', '11/21', '12/21', '13/21', '14/21', '15/21', '16/21', '17/21', '18/21', '19/21', '20/21', '21/21']
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
                text = await self.owner.safe_ocr(box=box, match=re.compile(".*", re.IGNORECASE),name="card_text")
                if text and '探索奖励' not in text[0].name:
                    logger.info("检测到卡牌文字需要点击空白关闭，点击")
                    await asyncio.sleep(1)
                    self.owner.click_relative_random(0.16, 0.41, 0.25, 0.56)

