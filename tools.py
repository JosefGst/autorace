# CODE IN THIS FILE IS GENERATED BY DONKEYCAR PROJECT
# https://github.com/autorope/donkeycar

from donkeycar.utils import *
import time
from donkeycar.parts.throttle_filter import ThrottleFilter
from donkeycar.parts.datastore import TubHandler
from donkeycar.parts.actuator import PCA9685, PWMSteering, PWMThrottle

def add_basic_modules(V, cfg):

    # return True when ai mode, otherwize respect user mode recording flag
    if cfg.RECORD_DURING_AI:
        V.add(AiRecordingCondition(), inputs=['user/mode', 'recording'], outputs=['recording'])

    # this throttle filter will allow one tap back for esc reverse
    th_filter = ThrottleFilter()
    V.add(th_filter, inputs=['user/throttle'], outputs=['user/throttle'])

    # add some other basic modules
    V.add(PilotCondition(), inputs=['user/mode'], outputs=['run_pilot'])
    rec_tracker_part = RecordTracker(cfg=cfg)
    V.add(rec_tracker_part, inputs=["tub/num_records"], outputs=[])

    return V

def add_tub_save_data(V, cfg):
    inputs=['cam/image_array',
            'user/angle', 'user/throttle',
            'user/mode']

    types=['image_array',
           'float', 'float',
           'str']

    if cfg.RECORD_DURING_AI:
        inputs += ['pilot/angle', 'pilot/throttle']
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

    throttle_controller = PCA9685(cfg.THROTTLE_CHANNEL, cfg.PCA9685_I2C_ADDR, busnum=cfg.PCA9685_I2C_BUSNUM)
    throttle = PWMThrottle(controller=throttle_controller,
                                    max_pulse=cfg.THROTTLE_FORWARD_PWM,
                                    zero_pulse=cfg.THROTTLE_STOPPED_PWM,
                                    min_pulse=cfg.THROTTLE_REVERSE_PWM)

    V.add(steering, inputs=['angle'], threaded=True)
    V.add(throttle, inputs=['throttle'], threaded=True)

    return V

#Choose what inputs should change the car.
class DriveMode:
    def __init__(self, cfg):
        self.cfg = cfg
    def run(self, mode,
                user_angle, user_throttle,
                pilot_angle, pilot_throttle):
        if mode == 'user':
            return user_angle, user_throttle

        elif mode == 'local_angle':
            return pilot_angle if pilot_angle else 0.0, user_throttle

        else:
            return pilot_angle if pilot_angle else 0.0, pilot_throttle * self.cfg.AI_THROTTLE_MULT if pilot_throttle else 0.0

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

    def run(self, num_records):
        if num_records is not None:
            if num_records % 10 == 0:
                print("recorded", num_records, "records")

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