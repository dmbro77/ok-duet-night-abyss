# Test case
import unittest

from src.config import config
from ok.test.TaskTestCase import TaskTestCase

from src.tasks.CommissionsTask import CommissionsTask


class TestMissonInterface(TaskTestCase):
    task_class = CommissionsTask

    config = config

    def test_feature1(self):
        self.set_image('tests/images/iface_esc.png')
        feature = self.task.find_esc_menu()
        self.assertIsNotNone(feature)
        self.logger.info(feature)

    def test_feature2(self):
        self.set_image('tests/images/iface_ltr_drop.png')
        feature = self.task.find_letter_reward_btn()
        self.assertIsNotNone(feature)
        self.logger.info(feature)

    def test_feature3(self):
        self.set_image('tests/images/iface_ltr.png')
        feature = self.task.find_letter_btn()
        self.assertIsNotNone(feature)
        self.logger.info(feature)

    def test_feature4(self):
        self.set_image('tests/images/iface_start.png')
        feature = self.task.find_bottom_start_btn()
        self.assertIsNotNone(feature)
        self.logger.info(feature)

    def test_feature5(self):
        self.set_image('tests/images/iface_cont.png')
        feature = self.task.find_ingame_continue_btn()
        self.assertIsNotNone(feature)
        self.logger.info(feature)

    def test_feature6(self):
        self.set_image('tests/images/iface_drop.png')
        feature = self.task.find_drop_item()
        self.assertIsNotNone(feature)
        self.logger.info(feature)



if __name__ == '__main__':
    unittest.main()
