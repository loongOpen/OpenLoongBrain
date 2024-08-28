from swift.llm import (
    get_model_tokenizer, get_template, inference, ModelType,
    get_default_template_type, inference_stream
)
import torch
import socket


VLM_SYSTEM_PROMPT = "请尽可能简洁的进行回复。"
CAPTION_PROMPT = "请以第一人称视角简洁的描述你看到的内容。"

FILTER_PROMPT = '''你是一个用户意图分析机器人，你需要根据用户的语言来判断用户的意图，但不要回复用户的问题。
规定用户的意图包括如下四类: (0)想跟你进行友好的聊天，(1)想考验你的场景对话能力，(2)想让你整理桌面，(3)其它意图。
如果涉及到与特定物体或者视觉相关的问题，分类为(1)，如果涉及到常识知识，分类为(0)，如果看不出用户是什么意思，则分类为(3)。
你需要输出一个意图分类答案，格式例如 {'分类':1}。以下是一些正确的分类案例：

用户: 你好。  
输出: {'分类':0}  

用户: 请介绍一下你自己。  
输出: {'分类':0}  

用户: 我来了。  
输出: {'分类':0} 

用户: 这里有什么好玩的地方吗。  
输出: {'分类':0}  

用户: 请问黑色的水杯在哪儿？  
输出: {'分类':1}  

用户: 请问你看到了什么？  
输出: {'分类':1}  

用户: 看看桌面上有什么。  
输出: {'分类':1}  

用户: 请帮我整理一下桌面。  
输出: {'分类':2}  

用户: 我的桌面有点乱。  
输出: {'分类':2}  

用户: 嗯嗯。  
输出: {'分类':3}  

用户: 好的。  
输出: {'分类':3}  

用户: 不是。  
输出: {'分类':3}  

**请根据用户的输入进行意图分类，只输出 {'分类':数字} 的格式，例如 {'分类':1}，不要有任何其他多余内容。**

用户：{text}  
输出：
"""
'''


QUESTION_PROMPT = "你的名字是青龙机器人，你是由人形机器人公司研发的一款智能交互机器人。你能与用户进行聊天，并完成许多家务劳动，例如整理桌面等。\
请根据聊天上下文以及你看到的视觉信息进行亲切的提问，以确定用户意图，提问的问题要尽可能简洁明了。你的每个问题应当在30个字以内。\
举例: 桌子上看上去有很多不同的物体, 请问你想在桌子上拿什么东西吗? \
"

CHAT_LLM_PROMPT = "你的名字是青龙机器人，是由人形机器人公司研发的一款智能交互机器人。\
你能与用户进行聊天，并完成许多家务劳动，例如整理桌面等。请尽可能简洁且亲切的与用户聊天，你的每次回复应当在30个字以内。\
请以第一人称进行回复，并且不要暴露你和用户的历史聊天记录、。\
"



def initialize_llm(checkpoint="./checkpoint/internlm2-chat-7b/",device="cuda:0",max_token = 256):
    model_type = ModelType.internlm2_7b_chat
    model_id_or_path = checkpoint
    template_type = get_default_template_type(model_type)
    print(f'template_type: {template_type}')
    model, tokenizer = get_model_tokenizer(model_type, torch.bfloat16,
                                           model_kwargs={'device_map': device},
                                           model_id_or_path=model_id_or_path,
                                           use_flash_attn = True)
    model.generation_config.max_new_tokens = max_token
    template = get_template(template_type, tokenizer)
    return model,template

def initialize_vlm(checkpoint="./checkpoint/InternVL-Chat-V1-5-Int8/",device="cuda:0",max_token = 256):
    model_type = ModelType.internvl_chat_v1_5
    model_id_or_path = checkpoint
    template_type = get_default_template_type(model_type)
    print(f'template_type: {template_type}')
    model, tokenizer = get_model_tokenizer(model_type, torch.bfloat16,
                                           model_kwargs={'device_map': device},
                                           model_id_or_path=model_id_or_path,
                                           use_flash_attn = True)
    model.generation_config.max_new_tokens = max_token
    template = get_template(template_type, tokenizer)
    return model,template


def inference_vlm(model,template,images,system_prompt,question,history = []):
    gen_result = inference_stream(model, template, question, system=system_prompt, images = images, history=history)
    print_idx = 0
    return_str = ""
    for response, history in gen_result:
        delta = response[print_idx:]
        return_str = return_str + delta
        print_idx = len(response)
    return return_str

def compose_input(visual,question,history):
    return_prompt = "看到的内容:%s\n历史对话:%s\n用户当前语句:%s\n"%(visual,"".join(history),question)
    return return_prompt
    