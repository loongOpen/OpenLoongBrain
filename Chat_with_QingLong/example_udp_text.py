import argparse
from socket import *
import os
import time
from threading import Thread, Lock
import queue
from collections import deque
import random
import base64
import hashlib
import threading
import uuid
import requests
from ws4py.client.threadedclient import WebSocketClient
import cv2
# from cv_bridge import CvBridge
import re
from pydub import AudioSegment
from pydub.playback import play
from io import BytesIO
import json

app_id = "YOUR_APP_ID"
api_key = "YOUR_API_KEY"

server_ip = 'YOUR_SERVER_IP'  # where llm models loaded（运行大模型的设备IP）
front_end_ip = 'YOUR_FRONT_END_IP'  # where your CAM connected（连接相机的设备IP）
# # qingloong:
robo_ip = '1YOUR_ROBO_IP'  # your control commands are sent to the robot at this IP（接受指令的机器人IP）

mutex1 = Lock()
mutex2 = Lock()
mutex3 = Lock()
mutex4 = Lock()


def capture_camera():
    # photo for VLM（相机拍照给多模态大模型）
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Cannot open camera")
        exit()

    ret, frame = cap.read()
    target_width = 640
    target_height = 480
    resized_gray = cv2.resize(frame, (target_width, target_height))

    if not ret:
        print("Can't receive frame (stream end?). Exiting ...")
        return

    cv2.imwrite('image.jpg', resized_gray)

    cap.release()
    cv2.destroyAllWindows()


def image_callback(msg):
    global to_send, mutex2
    bridge = CvBridge()
    cv_image = bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
    mutex2.acquire()
    if to_send:
        cv2.imwrite('image.jpg', cv_image)
        send_image('current.jpeg')
        to_send = False
        mutex2.release()
    else:
        mutex2.release()


def get_auth_id():
    mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
    return hashlib.md5(":".join([mac[e:e + 2] for e in range(0, 11, 2)]).encode("utf-8")).hexdigest()


data_type = "text"  ##
scene = "IFLYTEK.tts"  ##
file_path = r"demo.pcm"  # 用户自己收集
end_tag = "--end--"  # # 结束标识


class WsapiClient(WebSocketClient):

    def opened(self):
        pass

    def closed(self, code, reason=None):
        if code != 1000:
            print("连接异常关闭，code：" + str(code) + " ，reason：" + str(reason))

    def received_message(self, m):
        global text_msg
        s = json.loads(str(m))

        if s['action'] == "started":
            if (scene == "IFLYTEK.tts"):
                self.send(text_msg.encode("utf-8"))
            else:
                if (data_type == "text"):
                    self.send(text_msg.encode("utf-8"))

            # 数据发送结束之后发送结束标识sending
            self.send(bytes(end_tag.encode("utf-8")))

        elif s['action'] == "result":
            data = s['data']
            if data['sub'] == "tts":
                url = base64.b64decode(data['content']).decode()
                # Send a GET request to the URL
                response = requests.get(url)

                # Read the content of the response into a BytesIO buffer
                mp3_bytes = BytesIO(response.content)

                try:
                    # Load the MP3 file from the BytesIO buffer
                    audio = AudioSegment.from_file(mp3_bytes, format="mp3")
                    # Play the audio
                    play(audio)
                except:
                    print(f"## Decoding failed")
            else:
                print('exception occured')
        else:
            print('#### exception', s)


def user_input():
    global output_queue
    while True:
        question = input('请打字输入(Please type in):')
        output_queue.put(question)
        time.sleep(1)


def send_image(path):
    sock = socket(AF_INET, SOCK_DGRAM)
    server_address = (server_ip, 10002)

    with open(path, 'rb') as f:
        data = f.read()

    CHUNK_SIZE = 2048
    total_chunks = (len(data) // CHUNK_SIZE) + 1

    sock.sendto(total_chunks.to_bytes(4, byteorder='big'), server_address)

    for i in range(total_chunks):
        chunk = data[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]
        sock.sendto(chunk, server_address)
    print("current.jpg sent")
    time.sleep(0.01)
    sock.close()


def udp_server():
    global received_ans, mutex3, received_flag

    sock = socket(AF_INET, SOCK_DGRAM)
    server_address = (front_end_ip, 10001)
    sock.bind(server_address)
    print("UDP server up and listening at " + front_end_ip + ":10001")

    while 1:
        data, address = sock.recvfrom(4096)

        if received_flag:
            text = data.decode('utf-8')
            mutex3.acquire()
            received_ans.append(text)
            mutex3.release()

        time.sleep(0.05)


def udp_client():
    global sending2llm

    while 1:
        if len(sending2llm) > 0:
            message = sending2llm.popleft()
            sock = socket(AF_INET, SOCK_DGRAM)
            server_address = (server_ip, 10001)
            encoded_message = message.encode('utf-8')
            sent = sock.sendto(encoded_message, server_address)

        time.sleep(0.001)


class TTSManager:
    global tts_type

    def __init__(self):
        self.queue = queue.Queue()
        self.active = True
        self.thread = threading.Thread(target=self.process_queue)
        self.thread.start()
        self.path = os.getcwd()
        self.base_url = "ws://wsapi.xfyun.cn/v1/aiui"
        # 在 https://aiui.xfyun.cn/ 新建Webapi应用，并关闭IP白名单限制
        self.app_id = app_id
        self.api_key = api_key

    def start_tts(self, for_sending):
        self.queue.put(for_sending)

    def process_queue(self):
        while self.active or not self.queue.empty():
            try:
                for_sending = self.queue.get(timeout=1)
                self.run_tts(for_sending)
                self.queue.task_done()
            except queue.Empty:
                continue

    def run_tts(self, for_sending):
        global text_msg
        try:
            if tts_type == 'online_xunfei':

                text_msg = for_sending  #
                try:
                    # 构造握手参数
                    curTime = int(time.time())
                    auth_id = get_auth_id()
                    param_tts = """{{
                        "auth_id": "{0}",
                        "data_type": "text",
                        "vcn": "xiaoyan", 
                        "scene": "IFLYTEK.tts",
                        "tts_res_type": "url", 
                        "tts_aue" : "lame",
                        "speed": "50", 
                        "volume":"50", 
                        "context": "{{\\\"sdk_support\\\":[\\\"tts\\\"]}}"
                    }}"""
                    param = ""
                    if (scene == 'IFLYTEK.tts'):
                        param = param_tts.format(auth_id).encode(encoding="utf-8")

                    paramBase64 = base64.b64encode(param).decode()
                    checkSumPre = self.api_key + str(curTime) + paramBase64
                    checksum = hashlib.md5(checkSumPre.encode("utf-8")).hexdigest()
                    connParam = "?appid=" + self.app_id + "&checksum=" + checksum + "&param=" + paramBase64 + "&curtime=" + str(
                        curTime) + "&signtype=md5"
                    retry_count = 0
                    max_retries = 5
                    while retry_count < max_retries:
                        try:
                            ws = WsapiClient(self.base_url + connParam, protocols=['chat'],
                                             headers=[("Origin", "https://wsapi.xfyun.cn")])
                            ws.connect()
                            ws.run_forever()
                            break
                        except KeyboardInterrupt:
                            ws.close()
                        except Exception as e:
                            print(f"Exception in WebSocket client: {e}")
                            retry_count += 1
                            time.sleep(1)
                    if retry_count == max_retries:
                        print("Max retries reached. Could not establish WebSocket connection.")

                except KeyboardInterrupt:
                    print(f"exception in WebSocket client: {e}")
            else:
                print('异常tts type')
        except Exception as e:
            print(f"An error occurred while running TTS: {str(e)}")

    def stop(self):
        self.active = False  # 设置为False，结束处理循环
        self.thread.join()  # 等待线程结束
        print("TTS manager stopped.")

    def wait_until_done(self):
        self.queue.join()  # 等待队列中的所有项被处理完成


def has_punctuation(text):
    all_punctuation = "。.？?！!"  # 分段合成音频（Segmention）

    for i, char in enumerate(text):
        if char in all_punctuation:
            return True, i

    return False, -1


def generate():
    global for_sending
    global delta
    global received_ans, mutex3
    global tts_manager

    while 1:
        for_sending = ''

        while len(received_ans) > 0:
            mutex3.acquire()
            delta = received_ans.popleft()
            mutex3.release()

            pattern = r"\{'分类':[01234]\}"
            match = re.search(pattern, delta)
            if match:
                continue

            delta = re.sub(r'\*\*', '', delta)
            has_punc, punc_index = has_punctuation(delta)

            if not has_punc:
                for_sending = for_sending + delta
            else:
                for_sending += delta[:punc_index]
                print('***for_sending,', for_sending, time.time())
                mutex4.acquire()
                tts_manager.start_tts(for_sending)
                tts_manager.wait_until_done()
                mutex4.release()
                for_sending = delta[punc_index + 1:]

            time.sleep(0.01)

        mutex3.acquire()
        if len(for_sending) > 0:
            mutex3.release()
            tts_manager.start_tts(for_sending)
            tts_manager.wait_until_done()
            print('last=', for_sending)
        else:
            mutex3.release()

        time.sleep(0.01)


def main():
    global sending2llm
    global for_sending
    global delta
    global mutex1, mutex3, mutex2
    global received_flag
    global tts_manager
    global to_send

    exit_sent = False

    print('*********************Ready（系统准备完成）*********************')
    while True:

        mutex1.acquire()
        if not output_queue.empty():
            question = output_queue.get()
            mutex1.release()
            if not question:
                continue

            if not any(word in question for word in kill_dict):
                received_flag = True
                print('用户：', question, time.time())
                sending2llm.append(question + '.')

            else:  # 用户打断
                if not exit_sent:
                    print('***************************Interruption（出现打断）***************************')

                    mutex3.acquire()
                    for_sending = ''
                    delta = ''
                    received_ans.clear()
                    sending2llm.clear()
                    sending2llm.append("退出")

                    mutex3.release()
                    byebye = random.choice(bye_dict)
                    tts_manager.stop()
                    tts_manager = TTSManager()
                    tts_manager.start_tts(byebye)
                    tts_manager.wait_until_done()
                    exit_sent = True
                    while exit_sent:
                        received_flag = False
                        if not output_queue.empty():
                            question = output_queue.get()
                            if question == "你好":
                                received_flag = True
                                print('用户：', question, time.time())
                                sending2llm.clear()
                                sending2llm.append(question + '.')
                                exit_sent = False


        else:
            mutex1.release()
        time.sleep(0.001)


for_sending = ''
tts_manager = TTSManager()
received_ans = deque()
sending2llm = deque()
received_flag = True
to_send = False

kill_dict = ["退出"]

bye_dict = ["好的，再见", "好的，立刻为您退出", "好的，很高兴为您服务", "再见，祝您生活愉快", "正在为您退出",
            "再见，祝您一切顺利！", '已经为您退出了']

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--tts', type=str, default='online_xunfei')
    parser.add_argument('--input_type', type=str, required=True)
    config = vars(parser.parse_args())
    tts_type = config['tts']
    input_type = config['input_type']

    output_queue = queue.Queue()
    if input_type != 'text':
        from speech2text.main import *

        demo = SocketDemo(output_queue)
        thread1 = Thread(target=demo.process)  # with a Iflytex device（如果你连接了讯飞多模态语音识别模块）
    else:
        thread1 = Thread(target=user_input)  # alternatively, you can type in terminal（如果你没有买讯飞的产品，那你可以在命令行打字）
    thread1.start()  # thread1 for user commands（线程1收集用户指令）

    thread2 = Thread(target=generate)  # thread2 for TTS（线程2语音合成）
    thread2.start()

    thread3 = Thread(target=udp_server)  # thread3 for large models replay（线程3收集大模型回复）
    thread3.start()

    thread4 = Thread(target=udp_client)  # thread4 for sending commands to large models（线程4把指令发给大模型）
    thread4.start()

    main()

