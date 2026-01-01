import random
import re
import time

import cv2
from ok import Logger, TaskDisabledException, GenshinInteraction
from qfluentwidgets import FluentIcon

from src.common.icon_matcher import match_icon_in_screenshot,match_icon_special_symbols
from src.tasks.BaseAutoRouge import BaseAutoRouge
from src.tasks.DNAOneTimeTask import DNAOneTimeTask

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


class AutoRogueTask(BaseAutoRouge, DNAOneTimeTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.icon = FluentIcon.FLAG
        self.name = "自动80级 迷津"
        self.description = "全自动80级迷津，只能使用夫人"
        self.group_name = "全自动"
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
