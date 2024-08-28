import struct
from socket import *
import signal
from speech2text.processStrategy import *
import json
from collections import deque
import time
from threading import Lock



mutex1 = Lock()

def stop_handle(sig, frame):
    global run
    run = False


signal.signal(signal.SIGINT, stop_handle)
run = True
queue1 = deque()
currentSeq = -1

class SocketDemo:
    def __init__(self,output_queue):
        self.client_socket = socket(AF_INET, SOCK_STREAM)
        self.server_ip_port = ('YOUR_XUNFEI_IP', 19199) # IP of your XUNFEI device
        self.client_socket.connect(self.server_ip_port)
        self.output_queue=output_queue
        self.last_triggered = 0
        self.cooldown_period = 600  # Cooldown period in seconds (10 minutes)

    def close(self):
        self.client_socket.close()

    def parse(self, jsonObj):
        global queue1, currentSeq
        if jsonObj.get('type') == 'aiui_event' and isinstance(jsonObj.get('content'), dict) and isinstance(jsonObj['content'].get('info'), dict):
            print('识别开始',time.time())
  
            current_time = time.time()
            if isinstance(jsonObj['content']['info'].get('CMScore'), int):
                if (current_time - self.last_triggered) > self.cooldown_period:    
                    self.last_triggered = current_time
                    print('检测到有人靠近')# 十分钟之内，不重复触发
                    return '我来了'
                else:
                    print('Cooldown active, not triggering.')

            elif isinstance(jsonObj['content']['info'].get('data'), list):

                if jsonObj['content']['info']['data'][0]['params']['sub'] == 'iat':
                    result = jsonObj['content']['result']
                    rlt_flag = result['text']['rst']
                    ls_flag=result['text']['ls']
                    if rlt_flag == 'rlt' and ls_flag == False:
                        filtered_content = result['filtered']
                        print('start=',filtered_content)
                        print('识别结束',time.time())
                        return filtered_content
    
    def process(self):
        global mutex1
        while True:
            recv_data = self.client_socket.recv(4096)
            try:
                sync_head, user_id, msg_type, msg_length, msg_id = struct.unpack('<BBBHH', recv_data[:7])
            except:
                continue
            # 解析消息数据
            msg_data = recv_data[7:7 + msg_length]
            if sync_head == 0xa5 and user_id == 0x01:
                if msg_type == 0x01:
                    ConfirmProcess().process(self.client_socket, msg_id)
                elif msg_type == 0x04:
                    ConfirmProcess().process(self.client_socket, msg_id)
                    success, result = AiuiMessageProcess().process(self.client_socket, msg_data)
                    if success:
                        try:
                            jsonData = result.decode('utf-8')
                            jsonObj = json.loads(jsonData)
                        except Exception as e:
                            print("Exception: {}".format(e))
                            print(result)
                        mutex1.acquire()
                        self.output_queue.put(self.parse(jsonObj))
                        mutex1.release()