import zlib
from abc import abstractmethod, ABC


class ProcessStrategy(ABC):
    # 构建Msg
    def makepacket(self, sid, type, content):
        size = len(content)
        temp = bytearray()
        temp.append(0xa5)
        temp.append(0x01)
        temp.append(type)
        temp.append(size & 0xff)
        temp.append((size >> 8) & 0xff)
        temp.append(sid & 0xff)
        temp.append((sid >> 8) & 0xff)
        temp.extend(content)
        temp.append(self.checkcode(temp))
        # print(temp)
        return temp

    # 校验码计算
    def checkcode(self, data):
        total = sum(data)
        checkcode = (~total + 1) & 0xFF
        return checkcode

    @abstractmethod
    def process(self, client_socket, data):
        pass


# 确认消息
class ConfirmProcess(ProcessStrategy):
    def process(self, client_socket, msg_id):
        temp = bytearray()
        temp.append(0xa5)
        temp.append(0x00)
        temp.append(0x00)
        temp.append(0x00)
        send_data = self.makepacket(msg_id, 0xff, temp)
        client_socket.send(send_data)


# AIUI消息
class AiuiMessageProcess(ProcessStrategy):
    def process(self, client_socket, data):
        if not data:
            return False, bytearray()
        try:
            decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
            output = decompressor.decompress(data)
            output += decompressor.flush()
            return True, output
        except zlib.error as e:
            return False, bytearray()
