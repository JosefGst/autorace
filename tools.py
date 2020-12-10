# CODE IN THIS FILE IS GENERATED BY DONKEYCAR PROJECT
# https://github.com/autorope/donkeycar

from donkeycar.utils import *
import time
from donkeycar.parts.throttle_filter import ThrottleFilter
from donkeycar.parts.datastore import TubHandler
from donkeycar.parts.actuator import PCA9685, PWMSteering, PWMThrottle
from pid_controller.pid import PID
import numpy as np

def add_basic_modules(V, cfg):

    # return True when ai mode, otherwize respect user mode recording flag
    if cfg.RECORD_DURING_AI:
        V.add(AiRecordingCondition(), inputs=['user/mode', 'recording'], outputs=['recording'])

    # this throttle filter will allow one tap back for esc reverse
    th_filter = ThrottleFilter()
    V.add(th_filter, inputs=['user/vel_scalar'], outputs=['user/vel_scalar'])

    # add some other basic modules
    V.add(PilotCondition(), inputs=['user/mode'], outputs=['run_pilot'])
    rec_tracker_part = RecordTracker(cfg=cfg)
    V.add(rec_tracker_part, inputs=["tub/num_records"], outputs=[])
    V.add(AiRunCondition(), inputs=['user/mode'], outputs=['ai_running'])

    return V

def add_tub_save_data(V, cfg):
    inputs=['cam/image_array',
            'user/angle', 'user/vel_scalar',
            'user/mode']

    types=['image_array',
           'float', 'float',
           'str']
    
    if cfg.HAVE_UWB:
        inputs += [
            'imu/acl_x', 'imu/acl_y', 'imu/acl_z',
            'imu/gyr_x', 'imu/gyr_y', 'imu/gyr_z',
            'uwb/vel_x', 'uwb/vel_y', 'uwb/vel_z',
            'uwb/pose_x', 'uwb/pose_y', 'uwb/pose_z',
            'uwb/pose_unc_x', 'uwb/pose_unc_y', 'uwb/pose_unc_z',
            'uwb/ori_x', 'uwb/ori_y', 'uwb/ori_z', 'uwb/tag_id', 'uwb/voltage']

        types +=[
            'float', 'float', 'float',
            'float', 'float', 'float',
            'float', 'float', 'float',
            'float', 'float', 'float',
            'float', 'float', 'float',
            'float', 'float', 'float','float', 'float']

    if cfg.RECORD_DURING_AI:
        inputs += ['pilot/angle', 'pilot/vel_scalar']
        types += ['float', 'float']
    
    inputs += ['angle', 'throttle']
    types += ['float', 'float']

    th = TubHandler(path=cfg.DATA_PATH)
    tub = th.new_tub_writer(inputs=inputs, types=types)
    V.add(tub, inputs=inputs, outputs=["tub/num_records"], run_condition='recording')

    return V, tub

def add_control_modules(V, cfg):
    steering_controller = PCA9685(cfg.STEERING_CHANNEL, cfg.PCA9685_I2C_ADDR, busnum=cfg.PCA9685_I2C_BUSNUM)
    steering = PWMSteering(controller=steering_controller,
                                    left_pulse=cfg.STEERING_LEFT_PWM,
                                    right_pulse=cfg.STEERING_RIGHT_PWM)

    throttle_controller = PCA9685(1, cfg.PCA9685_I2C_ADDR, busnum=cfg.PCA9685_I2C_BUSNUM)
    throttle = PWMThrottle(controller=throttle_controller)

    V.add(steering, inputs=['angle'], threaded=True)
    V.add(throttle, inputs=['throttle'], threaded=True)

    return V

#Choose what inputs should change the car.
class DriveMode:
    def __init__(self, cfg):
        self.cfg = cfg
        self.params = {
            'default_throttle': 0.2,  # Default Throttle
            'pid_p': 0.22,  # PID speed controller parameters
            'pid_i': 0.3,  # 0.2
            'pid_d': 0.0,
            'throttle_max': 0.75,
            'speed_indicator': 2
        }
        # PID speed controller
        self.pid = PID(p=self.params['pid_p'], i=self.params['pid_i'], d=self.params['pid_d'])
    
    def cal_throttle(self, current_speed, target_speed):
        if target_speed >= 1.4:
            default_throttle = 0.25
            min_throttle = 0.15
        elif 1.0 < target_speed < 1.4:
            default_throttle = 0.2
            min_throttle = 0.05
        elif 0.6 <= target_speed <= 1.0:
            default_throttle = 0.12
            min_throttle = 0.03
        else:
            default_throttle = 0.05
            min_throttle = 0.015
        self.pid.target = target_speed
        pid_gain = self.pid(feedback=current_speed)

        throttle = min(max(default_throttle - 1.0 * pid_gain, min_throttle),
                       self.params['throttle_max'])

        return throttle

    def run(self, mode,
                user_angle, user_vel_scalar,
                pilot_angle, pilot_vel_scalar, vel_x, vel_y):
        
        current_speed = np.sqrt(vel_x**2 + vel_y**2)
        print('vel: %.1f'%current_speed, end=' | ')
        
        if mode == 'user':
            if user_vel_scalar > 0:
                target_speed = user_vel_scalar * self.params['speed_indicator']
                user_throttle = self.cal_throttle(current_speed, target_speed)
            else:
                user_throttle = user_vel_scalar 
            print(user_throttle)
            return user_angle, user_throttle

        elif mode == 'local_angle':
            if user_vel_scalar > 0:
                target_speed = user_vel_scalar * self.params['speed_indicator']
                user_throttle = self.cal_throttle(current_speed, target_speed)
            else:
                user_throttle = user_vel_scalar

            return pilot_angle if pilot_angle else 0.0, user_throttle

        else:
            if pilot_vel_scalar:
                if pilot_vel_scalar > 0:
                    target_speed = pilot_vel_scalar * self.params['speed_indicator']
                    pilot_throttle = self.cal_throttle(current_speed, target_speed) * self.cfg.AI_THROTTLE_MULT
                else:
                    pilot_throttle = pilot_vel_scalar
            else:
                pilot_throttle = 0

            return pilot_angle if pilot_angle else 0.0, pilot_throttle

class AiRunCondition:
    '''
    A bool part to let us know when ai is running.
    '''
    def run(self, mode):
        if mode == "user":
            return False
        return True

class AiRecordingCondition:
    '''
    return True when ai mode, otherwize respect user mode recording flag
    '''
    def run(self, mode, recording):
        if mode == 'user':
            return recording
        return True

def get_record_alert_color(num_records):
    col = (0, 0, 0)
    for count, color in cfg.RECORD_ALERT_COLOR_ARR:
        if num_records >= count:
            col = color
    return col

class RecordTracker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.last_record_num = -100

    def run(self, num_records):
        if num_records is not None:
            if num_records % 10 == 0 and num_records != self.last_record_num:
                print("recorded", num_records, "records")
                self.last_record_num = num_records

#See if we should even run the pilot module.
#This is only needed because the part run_condition only accepts boolean
class PilotCondition:
    def run(self, mode):
        if mode == 'user':
            return False
        else:
            return True

class ImgPreProcess():
    '''
    preprocess camera image for inference.
    normalize and crop if needed.
    '''
    def __init__(self, cfg):
        self.cfg = cfg

    def run(self, img_arr):
        return normalize_and_crop(img_arr, self.cfg)