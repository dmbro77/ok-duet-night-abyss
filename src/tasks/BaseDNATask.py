import time
import numpy as np
import cv2
import winsound

from ok import BaseTask, Box

class BaseDNATask(BaseTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.key_config = self.get_global_config('Game Hotkey Config')  # 游戏热键配置
        self.afk_config = self.get_global_config('挂机设置')

    def in_team(self) -> bool:
        if self.find_one('lv_text', threshold=0.8):
            return True
        return False
    
    def find_start_btn(self, threshold: float = 0, box: Box | None = None) -> Box | None:
        return self.find_one('start_icon', threshold=threshold, box=box)
    
    def find_cancel_btn(self, threshold: float = 0, box: Box | None = None) -> Box | None:
        return self.find_one('cancel_icon', threshold=threshold, box=box)
    
    def find_retry_btn(self, threshold: float = 0, box: Box | None = None) -> Box | None:
        return self.find_one('retry_icon', threshold=threshold, box=box)
    
    def find_quit_btn(self, threshold: float = 0, box: Box | None = None) -> Box | None:
        return self.find_one('quit_icon', threshold=threshold, box=box)
    
    def wait_click_start_btn(self, threshold: float = 0, time_out: float = 0, box: Box | None = None, raise_if_not_found: bool = True) -> bool:
        return self.wait_click_feature('start_icon', threshold=threshold, time_out=time_out, box=box, raise_if_not_found=raise_if_not_found)
    
    def wait_click_cancel_btn(self, threshold: float = 0, time_out: float = 0, box: Box | None = None, raise_if_not_found: bool = True) -> bool:
        return self.wait_click_feature('cancel_icon', threshold=threshold, time_out=time_out, box=box, raise_if_not_found=raise_if_not_found)
    
    def wait_click_retry_btn(self, threshold: float = 0, time_out: float = 0, box: Box | None = None, raise_if_not_found: bool = True) -> bool:
        return self.wait_click_feature('retry_icon', threshold=threshold, time_out=time_out, box=box, raise_if_not_found=raise_if_not_found)

    def wait_click_quit_btn(self, threshold: float = 0, time_out: float = 0, box: Box | None = None, raise_if_not_found: bool = True) -> bool:
        return self.wait_click_feature('quit_icon', threshold=threshold, time_out=time_out, box=box, raise_if_not_found=raise_if_not_found)
    
    def click_until(self, click_func: callable, check_func: callable, check_interval: float = 2, time_out: float = 10):
        start = time.time()
        while time.time() - start < time_out:
            click_func()
            if self.wait_until(check_func, time_out=check_interval, raise_if_not_found=False):
                break
        else:
            raise Exception("click_until timeout")

    def safe_get(self, key, default=None):
        if hasattr(self, key):
            return getattr(self, key)
        return default

    def soundBeep(self):
        if hasattr(self, "config") and not self.config.get('发出声音提醒', True):
            return
        n = self.afk_config['提示音'] if self.afk_config['提示音'] > 0 else 1
        for _ in range(n):
            winsound.Beep(523, 150)
            self.sleep(0.3)


lower_white = np.array([244, 244, 244], dtype=np.uint8)
lower_white_none_inclusive = np.array([243, 243, 243], dtype=np.uint8)
upper_white = np.array([255, 255, 255], dtype=np.uint8)
black = np.array([0, 0, 0], dtype=np.uint8)

def isolate_white_text_to_black(cv_image):
    """
    Converts pixels in the near-white range (244-255) to black,
    and all others to white.
    Args:
        cv_image: Input image (NumPy array, BGR).
    Returns:
        Black and white image (NumPy array), where matches are black.
    """
    match_mask = cv2.inRange(cv_image, black, lower_white_none_inclusive)
    output_image = cv2.cvtColor(match_mask, cv2.COLOR_GRAY2BGR)

    return output_image
