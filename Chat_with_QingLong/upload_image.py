import cv2
import requests

# 定义视频捕获对象
cap = cv2.VideoCapture(0)

# 定义目标URL
url = 'your/server/ip:5000/upload'  # 使用服务器的IP地址

while True:
    # 读取视频帧
    ret, frame = cap.read()

    # 检查是否成功读取帧
    if not ret:
        break

    # 将帧编码为JPEG格式
    ret, buffer = cv2.imencode('.jpg', frame)

    # 将图像转换为字节格式
    image_bytes = buffer.tobytes()

    # 准备HTTP POST请求的文件部分
    files = {'file': ('image.jpg', image_bytes, 'image/jpeg')}

    # 发送POST请求
    response = requests.post(url, files=files)

    # 打印响应状态码
    print(response.status_code)

    # 显示视频帧（添加这行以显示当前捕获的帧）
    cv2.imshow('Frame', frame)

    # 按键退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("Exit key pressed")
        break

# 释放视频捕获对象并关闭所有窗口
cap.release()
cv2.destroyAllWindows()
