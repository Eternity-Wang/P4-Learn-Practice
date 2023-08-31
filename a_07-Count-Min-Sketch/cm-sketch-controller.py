import socket, struct, pickle, os
from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import *
from crc import Crc

crc32_polinomials = [0x04C11DB7, 0xEDB88320, 0xDB710641, 0x82608EDB, 0x741B8CD7, 0xEB31D82E,
                     0xD663B05, 0xBA0DC66B, 0x32583499, 0x992C1A4C, 0x32583499, 0x992C1A4C]

class CMSController(object):

    def __init__(self, sw_name, set_hash):

        self.topo = load_topo('topology.json')
        self.sw_name = sw_name
        self.set_hash = set_hash
        self.thrift_port = self.topo.get_thrift_port(sw_name)
        self.controller = SimpleSwitchThriftAPI(self.thrift_port)
       
        # 获取交换机中自定义的 crc 算法的列表
        self.custom_calcs = self.controller.get_custom_crc_calcs()
        # 根据 custom_calcs 获取寄存器的数量(本例中二者的数量是一一对应的)
        self.register_num = len(self.custom_calcs)

        self.init()
        self.registers = []

    def init(self):

        ''' 对crc自定义的哈希算法进行初始化 '''

        # 首先将那些自定义crc32哈希算法在交换机中进行设置
        if self.set_hash:
            self.set_crc_custom_hashes()

        # 接着在 python 中也创建相应的算法(与数据平面中所设置的算法一一对应)
        self.create_hashes()

    def set_forwarding(self):

        ''' 设置fwb_tbl表的相关表项 '''

        self.controller.table_add("fwb_tbl", "set_egress_port", ['1'], ['2'])
        self.controller.table_add("fwb_tbl", "set_egress_port", ['2'], ['1'])

    def reset_registers(self):

        ''' 重置交换机中的所有寄存器 '''

        for i in range(self.register_num):
            self.controller.register_reset("sketch{}".format(i))

    def flow_to_bytestream(self, flow):

        ''' 将流 flow 转换为字节流的形式 '''

        return socket.inet_aton(flow[0]) + socket.inet_aton(flow[1]) + struct.pack(">HHB",flow[2], flow[3], 6)

    def set_crc_custom_hashes(self):

        ''' 对交换机中的那些自定义的crc哈希算法进行设置 '''

        i = 0
        # 从已经排好序的自定义算法列表中依次取出单个 item
        # (即custom_crc32, 一个自定义的crc32哈希算法)
        for custom_crc32, width in sorted(self.custom_calcs.items()):
            # 对custom_crc32的有关参数进行设置, 即实现了自定义算法(区别在于极化多项式的值不同)
            self.controller.set_crc32_parameters(custom_crc32, crc32_polinomials[i], 0xffffffff, 0xffffffff, True, True)
            i += 1

    def create_hashes(self):

        ''' 创建一个hashes列表, 列表中的每个元素都是一个自定义的crc32哈希函数 '''

        self.hashes = []
        print("寄存器的数量为:", self.register_num)
        for i in range(self.register_num):
            self.hashes.append(Crc(32, crc32_polinomials[i], True, 0xffffffff, True, 0xffffffff))

    def read_registers(self):

        ''' 读取每个寄存器中的所有值, 并存放到registers这个列表中 '''

        self.registers = []
        for i in range(self.register_num):
            self.registers.append(self.controller.register_read("sketch{}".format(i)))

    def get_cms(self, flow, mod):

        ''' 对每个寄存器中的数值进行读取/检索, 然后返回它们之间的最小值 '''

        # 存放从寄存器中的对应索引处读取到的值
        reg_count = []

        # 从输入的流的五元组中生成相应的字节流
        out_bs = self.flow_to_bytestream(flow)
        for i in range(self.register_num):
            hash_output = self.hashes[i].bit_by_bit_fast(out_bs) % mod
            reg_count.append(self.registers[i][hash_output])
        print("收集到的各个寄存器中的值为:", reg_count)

        # 返回列表中的最小值
        return min(reg_count)

    def decode_registers(self, eps, n, mod, ground_truth_file="sent_flows.pickle"):
        
        ''' 将 CMS 所计数出来的值与实际发送的数据包数量进行比较 '''

        self.read_registers()
        flows = pickle.load(open(ground_truth_file, "rb"))
        for flow, real_count in flows.items():
            print("当前流的四元组为:", flow)
            cms_count = self.get_cms(flow, mod)
            print("实际发送的数据包数量:", real_count)
            print("由 Count-min Sketch 所记录的数据包数量:", cms_count)
            print("=================================")

if __name__ == "__main__":

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--sw', help="需要进行配置的交换机名称" , type=str, required=False, default="s1")
    parser.add_argument('--eps', help="检查边界时使用的epsilon", type=float, required=False, default=0.01)
    parser.add_argument('--n', help="由send.py发送的数据包数量", type=int, required=False, default=1000)
    parser.add_argument('--mod', help="每个寄存器的大小", type=int, required=False, default=4096)
    parser.add_argument('--flow-file', help="由send.py生成的文件的文件名", type=str, required=False, default="sent_flows.pickle")
    parser.add_argument('--option', help="控制器选项可以是set_hashes、decode或reset registers", type=str, required=False, default="set_hashes")
    args = parser.parse_args()

    # 默认的option参数为"set_hashes"，此时控制器所作的操作是配置交换机中的哈希函数
    set_hashes = args.option == "set_hashes"
    # 实例化一个 CMSController 类的对象
    controller = CMSController(args.sw, set_hashes)

    if args.option == "decode":
        controller.decode_registers(args.eps, args.n, args.mod, args.flow_file)

    elif args.option == "reset":
        controller.reset_registers()