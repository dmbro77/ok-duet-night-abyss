from ok import TriggerTask, Logger, og
from src.tasks.BaseCombatTask import BaseCombatTask, NotInCombatException, CharDeadException

from pynput import mouse, keyboard
logger = Logger.get_logger(__name__)

class TriggerDeactivateException(Exception):
    """未处于战斗状态异常。"""
    pass

class AutoMoveTask(BaseCombatTask, TriggerTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动穿引共鸣"
        self.description = "需使用鼠标侧键主动激活"
        self.default_config.update({
            '激活键': 'x1',
            '按下时间': 0.50,
            '间隔时间': 0.45,
        })
        self.config_type['激活键'] = {'type': 'drop_down', 'options': ['x1', 'x2']}
        self.config_description.update({
            '激活键': '鼠标侧键',
            '按下时间': '左键按住多久',
            '间隔时间': '左键释放后等待多久',
        })
        self.listener = None
        self.manual_activate = False
        self.is_down = False
        self._executor.exit_event.bind_stop(self)

    def disable(self):
        super().disable()
        self.stop()

    def pause(self):
        super().pause()
        self.stop()

    def stop(self):
        self.manual_activate = False
        if self.listener:
            self.listener.stop()
            self.listener = None
    
    def run(self):
        if not self.in_team():
            return
        
        if not self.listener:
            self.listener = mouse.Listener(on_click=self.on_click)
            # self.listener = keyboard.Listener(on_press=self.on_press)
            self.listener.start()

        while self.manual_activate:
            try:
                self.do_move()
            except CharDeadException:
                self.log_error(f'Characters dead', notify=True)
                break
            except TriggerDeactivateException as e:
                logger.info(f'auto_move_task_deactivate {e}')
                break
        if self.is_down:
            self.mouse_up()
        return 
    
    def do_move(self):
        self.mouse_down()
        self.is_down = True
        self.sleep(self.config.get('按下时间', 0.50))
        self.mouse_up()
        self.is_down = False
        self.sleep_check(self.config.get('间隔时间', 0.45))

    def sleep_check(self, sec):
        remaining = sec
        step = 0.2
        while remaining > 0:
            s = step if remaining > step else remaining
            self.sleep(s)
            remaining -= s
            if not self.manual_activate:
                raise TriggerDeactivateException()
        
    def on_click(self, x, y, button, pressed):
        if self._executor.paused:
            return
        if not self.in_team() or not og.device_manager.hwnd_window.is_foreground():
            return
        if self.config.get('激活键', 'x2') == 'x1':
            btn = mouse.Button.x1
        else:
            btn = mouse.Button.x2
        if pressed and button == btn:
            self.manual_activate = not self.manual_activate
            if self.manual_activate:
                logger.info("激活快速移动")
            else:
                logger.info("关闭快速移动")

    # def on_press(self, key):
    #     if self._executor.paused:
    #         return
    #     if not self.in_team() or not og.device_manager.hwnd_window.is_foreground():
    #         return
    #     active_key = getattr(keyboard.Key, self.config.get('激活键').lower())
    #     if key == active_key:
    #         self.manual_activate = not self.manual_activate
    #         if self.manual_activate:
    #             logger.info("激活快速移动")
    #         else:
    #             logger.info("关闭快速移动")



