# 主论坛发布会！ 6月30日
import threading
import ast
import time
import socket
import os
from utils_p import initialize_llm, compose_input, FILTER_PROMPT, CHAT_LLM_PROMPT, QUESTION_PROMPT
from utils_p import initialize_vlm, CAPTION_PROMPT, VLM_SYSTEM_PROMPT
from swift.llm import (
    get_model_tokenizer, get_template, inference, ModelType,
    get_default_template_type, inference_stream
)

from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol
from openloong import openloong

server_ip = 'YOUR_SERVER_IP'
front_end_ip = 'YOUR_FRONT_END_IP'
# qinglong:
robo_ip = 'YOUR_ROBO_IP'

DEBUG = True


class QingLong_Agent():
    def __init__(self,
                 memory_size=4,
                 max_tokens=512,
                 devices=[0, 1],
                 tts_address=(front_end_ip, 10001),
                 audio_address=(server_ip, 10001),
                 image_address=(server_ip, 10002),
                 function_adress=(front_end_ip, 10003),
                 internlm_checkpoint="./checkpoint/internlm2-chat-7b/",
                 internvl_checkpoint="./checkpoint/InternVL-Chat-V1-5-Int8/",
                 ):
        self.memory_size = memory_size
        self.max_tokens = max_tokens
        self.llm_device = "cuda:%d" % devices[0]
        self.vlm_device = "cuda:%d" % devices[1]
        self.tts_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tts_server_address = tts_address

        self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.audio_server_address = audio_address
        self.audio_socket.bind(self.audio_server_address)

        self.image_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.image_server_address = image_address
        self.image_socket.bind(self.image_server_address)

        self.function_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.function_server_address = function_adress

        self.internlm_model, self.internlm_template = initialize_llm(internlm_checkpoint, self.llm_device,
                                                                     self.max_tokens)
        self.internvl_model, self.internvl_template = initialize_vlm(internvl_checkpoint, self.vlm_device,
                                                                     self.max_tokens)
        self.user_chat_history = []
        self.bot_chat_history = []

        self.image_path = 'upload/image.jpg'
        self.image_caption = ""
        self.user_input = None
        self.attempt_code = None
        self.running_status = True
        self.llm_flag = False
        self.vlm_flag = False

        self.send_flag = True
        self.print_flag = True

        self.transport = TSocket.TSocket(robo_ip, 9090)
        self.transport = TTransport.TBufferedTransport(self.transport)
        self.protocol = TBinaryProtocol.TBinaryProtocol(self.transport)
        self.client = openloong.Client(self.protocol)

        self.exit_mode = False

    def inference_llm(self, system_prompt, question, send_flag=True, print_flag=True, history=[]):

        if self.exit_mode and question != "你好":
            return ""

        status = "init"  # 初始化状态
        gen_result = inference_stream(self.internlm_model, self.internlm_template, query=question, system=system_prompt,
                                      history=history)
        print_idx = 0
        num_delta = 0
        return_str = ""
        for response, _ in gen_result:
            delta = response[print_idx:]
            if delta:
                num_delta += 1
                return_str = return_str + delta
                print_idx = len(response)
                if status == "init":
                    if print_flag:
                        print(delta, end='', flush=True)
                    status = "ready"
                    continue
                elif status == "ready":
                    if send_flag:
                        self.tts_socket.sendto(return_str.encode('utf-8'), self.tts_server_address)
                        # print("===message already sent====")
                    if print_flag:
                        print(delta, end='', flush=True)
                    status = "done"
                else:
                    if send_flag:
                        self.tts_socket.sendto(delta.encode('utf-8'), self.tts_server_address)
                        # print("===message already sent====")
                    if print_flag:
                        print(delta, end='', flush=True)

        # print(f"num_delta = {num_delta},delta={delta}")
        if num_delta == 1 and '{\'分类\':' not in delta:
            print(delta)
            self.tts_socket.sendto(delta.encode('utf-8'), self.tts_server_address)
            print(f"delta只有一个真实值，输出========{delta}")
            status = "done"

        return return_str

    def inference_vlm(self, system_prompt, question, image, send_flag=True, print_flag=True, history=[]):
        status = "ready"  # 初始化状态
        gen_result = inference_stream(self.internvl_model, self.internvl_template, query=question, system=system_prompt,
                                      images=[image], history=history)
        print_idx = 0
        return_str = ""
        for response, _ in gen_result:

            delta = response[print_idx:]
            if delta:
                return_str = return_str + delta
                print_idx = len(response)
                if status == "init":
                    if print_flag:
                        print(delta, end='', flush=True)
                    status = "ready"
                    print('等待\n')
                    continue
                elif status == "ready":
                    if send_flag:
                        self.tts_socket.sendto(return_str.encode('utf-8'), self.tts_server_address)
                        # print("===message already sent====")
                    if print_flag:
                        print(delta, end='', flush=True)
                    status = "done"
                else:
                    if send_flag:
                        self.tts_socket.sendto(delta.encode('utf-8'), self.tts_server_address)
                        # print("===message already sent====")
                    if print_flag:
                        print(delta, end='', flush=True)
        return return_str

    # for receiving the texts from xunfei api
    def audio_listener(self):
        print('audio-listen')
        while self.running_status:
            print('received_while_flag=', self.running_status)
            data, _ = self.audio_socket.recvfrom(4096)
            self.user_input = data.decode('utf-8')
            print('received_msg=', self.user_input)

            if "退出" in self.user_input:
                self.exit_mode = True
                continue

            if "你好" in self.user_input:
                self.exit_mode = False
                self.user_chat_history.clear()
                self.bot_chat_history.clear()

                self.running_status = True
            self.user_chat_history.append(self.user_input)
            if len(self.user_chat_history) > self.memory_size:
                if len(self.bot_chat_history) > 0:
                    del self.bot_chat_history[0]
                if len(self.user_chat_history) > 0:
                    del self.user_chat_history[0]
            time.sleep(0.001)

    def attempt_listener(self):
        while self.running_status:
            if self.user_input is not None and self.user_input[-1] in ['.', '!', '?', ',']:
                while True:
                    try:
                        attempt_str = self.inference_llm(FILTER_PROMPT, self.user_input, False, True)
                        attempt_dict = ast.literal_eval(attempt_str)
                        self.attempt_code = int(attempt_dict['分类'])
                        break
                    except:
                        pass
                self.user_input = None
            time.sleep(0.001)

    def compose_history(self):
        new_list = []
        for i in range(min(len(self.user_chat_history), len(self.bot_chat_history))):
            new_list.append((self.user_chat_history[i], self.bot_chat_history[i]))
        return new_list

    def compose_vision(self):
        new_string = "视觉信息:%s\n用户问题:%s\n" % (self.image_caption, self.user_chat_history[-1])
        return new_string

    def execute_listener(self):
        while self.running_status:
            if self.attempt_code is not None and self.attempt_code == 0 and self.llm_flag == False:
                self.llm_flag = True
                response = self.inference_llm(CHAT_LLM_PROMPT, self.user_chat_history[-1], self.send_flag,
                                              self.print_flag, history=self.compose_history())
                self.bot_chat_history.append(response)
                self.llm_flag = False
                self.attempt_code = None
            elif self.attempt_code is not None and self.attempt_code == 1 and self.vlm_flag == False:
                self.vlm_flag = True
                response = self.inference_vlm(VLM_SYSTEM_PROMPT, self.user_chat_history[-1], self.image_path,
                                              self.send_flag, self.print_flag)
                self.bot_chat_history.append(response)
                self.vlm_flag = False
                self.attempt_code = None
                # =======
            elif self.attempt_code is not None and self.attempt_code == 2 and self.llm_flag == False:
                self.llm_flag = True
                response = '正在为您整理桌面'
                # 调用整理桌面函数
                if not DEBUG:
                    print(f"******调用的函数为: ***grasp_all***")
                    self.transport.open()
                    self.client.t_action_grasp_all(100)
                    time.sleep(40)
                    print("[LLM]reset arm")
                    self.client.t_action_safe()  # 7
                    time.sleep(0.5)

                    self.transport.close()
                    print("[LLM] finish")

                self.tts_socket.sendto(response.encode('utf-8'), self.tts_server_address)
                print(response)
                self.bot_chat_history.append(response)
                self.llm_flag = False
                self.attempt_code = None

            elif self.attempt_code is not None and self.attempt_code == 3 and self.llm_flag == False:
                self.llm_flag = True
                response = self.inference_llm(QUESTION_PROMPT, self.compose_vision(), self.send_flag, self.print_flag,
                                              history=self.compose_history())
                self.bot_chat_history.append(response)
                self.llm_flag = False
                self.attempt_code = None
            time.sleep(0.001)

    def caption_listener(self):
        while self.running_status:
            if self.vlm_flag == False:
                self.vlm_flag == True
                content = self.inference_vlm(CAPTION_PROMPT, "", self.image_path, False, False)
                self.image_caption = content
                time.sleep(0.01)


if __name__ == '__main__':
    agent = QingLong_Agent()
    thread_audio2text = threading.Thread(target=agent.audio_listener)
    thread_audio2text.start()
    thread_classify = threading.Thread(target=agent.attempt_listener)
    thread_classify.start()
    thread_execute = threading.Thread(target=agent.execute_listener)
    thread_execute.start()





