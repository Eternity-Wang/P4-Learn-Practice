#!/usr/bin/env python3
import socket
import random
import os
import struct
import fcntl

class TimeoutError(Exception):
    pass

#### DEFINITION OF TCP,UDP,ICMP, AND IP CLASSES. I use them to parse headers.
class iphdr(object):
    """
    这个类代表一个 IP 数据包的报头
    @assemble 用于打包数据包
    @disassemble 用于拆解数据包
    """
    def __init__(self, proto=socket.IPPROTO_ICMP, src="0.0.0.0", dst=None):

        ''' IP 报头的初始化函数 '''

        self.version = 4
        self.hlen = 5
        self.tos = 128
        self.length = 20
        self.id = random.randint(2 ** 10, 2 ** 16)
        self.frag = 0
        self.ttl = 255
        self.proto = proto
        self.cksum = 0
        self.src = src
        self.saddr = socket.inet_aton(src)
        self.dst = dst or "0.0.0.0"
        self.daddr = socket.inet_aton(self.dst)
        self.data = ""

    @classmethod
    def disassemble(self, data):
        
        ''' 对接收到的数据包的 IP 报头进行拆解, 并将解析后的值依次赋予给报头中对应的字段 '''

        # DATA 必须是接收到的数据包 packet[:20] 的前 20 个字节
        # 或 packet[28:48]（如果这是引用的 ip 报头）
 
        # 首先初始化一个 IP 报头, 用于存放解析后的值
        ip = iphdr()
        # 对数据包的前 12 个字节进行解析
        pkt = struct.unpack('!BBHHHBBH', data[:12])
        ip.version = (pkt[0] >> 4 & 0x0f)
        ip.hlen = (pkt[0] & 0x0f)
        ip.tos, ip.length, ip.id, ip.frag, ip.ttl, ip.proto, ip.cksum = pkt[1:]
        # 提取字节对象形式的源 IP 地址和目的 IP 地址
        ip.saddr = data[12:16]
        ip.daddr = data[16:20]
        # 将 ip.saddr 和 ip.daddr 分别转换为点分四组形式的 IP 地址
        ip.src = socket.inet_ntoa(ip.saddr)
        ip.dst = socket.inet_ntoa(ip.daddr)
        # 返回解析后的 IP 报头
        return ip

class tcphdr(object):
    def __init__(self, data="", dport=4242, sport=4242):

        ''' TCP 报头的初始化函数 '''

        self.seq = 0
        self.hlen = 44
        self.flags = 2
        self.wsize = 200
        self.cksum = 123
        self.options = 0
        self.mss = 1460
        self.dport = dport
        self.sport = sport
        self.data = data

    @classmethod
    def disassemble(self, data):
        
        ''' 对接收到的数据包的 TCP 报头进行拆解, 并将解析后的值依次赋予给报头中对应的字段 '''

        # 首先初始化一个 TCP 报头, 用于存放解析后的值
        tcp = tcphdr()
        # 对接收到的数据包进行解析(具体想要解析的数据可以自行编写)

        #pkt = struct.unpack("!HHLLBBHHH", data)
        pkt = struct.unpack("!HHL", data)

        tcp.sport, tcp.dport, tcp.seq = pkt[0],pkt[1], pkt[2]
        #tcp.ack = pkt[3]
        
        # 返回解析后的 TCP 报头 
        return tcp


class udphdr(object):
    def __init__(self, data="", dport=4242, sport=4242):

        ''' UDP 报头的初始化函数 '''

        self.dport = dport
        self.sport = sport
        self.cksum = 0
        self.length = 0
        self.data = data

    @classmethod
    def disassemble(self, data):

        ''' 对接收到的数据包的 UDP 报头进行拆解, 并将解析后的值依次赋予给报头中对应的字段 '''

        udp = udphdr()

        pkt = struct.unpack("!HHHH", data)

        udp.sport, udp.dport, udp.length, udp.cksum = pkt
        return udp

class icmphdr(object):
    def __init__(self, data=""):

        ''' ICMP 报头的初始化函数 '''

        self.type = 8
        self.code = 0
        self.cksum = 0
        self.id = random.randint(2 ** 10, 2 ** 16)
        self.sequence = 0
        self.data = data

    @classmethod
    def disassemble(self, data):

        ''' 对接收到的数据包的 ICMP 报头进行拆解, 并将解析后的值依次赋予给报头中对应的字段 '''

        # 如果是第一个 ICMP 报头，则必须从 data 的 20:28 开始进行解析(即占用 8 个字节)

        icmp = icmphdr()

        pkt = struct.unpack("!BBHHH", data)

        icmp.type, icmp.code, icmp.cksum, icmp.id, icmp.sequence = pkt
        return icmp


def checksum(msg):

    ''' 用于计算校验和的函数 '''
    s = 0
    # 每次循环将取 2 个字符
    for i in range(0, len(msg), 2):
        w = (msg[i] << 8) + msg[i+1]
        s = s + w

    s = (s>>16) + (s & 0xffff)
    #s = s + (s >> 16)   补码和掩码为 4 字节
    s = ~s & 0xffff

    return s


def get_ip_address(ifname):

    ''' 根据端口号来获取 IP 地址 '''

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack(b'256s', ifname[:15].encode())
    )[20:24])


def ip_header(src,dst,ttl,proto,id=0):

    ''' IP 报头 '''

    # 现在开始构建数据包
    packet = ''
    
    # IP 报头的各个字段
    ihl = 5
    version = 4
    tos = 128
    tot_len = 20 + 20   # python 似乎正确地填充了总长度，不知道为何？
    frag_off = 0

    # IP 报头的 proto 字段的值, 在本例中即 UDP 或 TCP
    if proto == "tcp":
        proto = socket.IPPROTO_TCP
    elif proto == "udp":
        proto = socket.IPPROTO_UDP
    else:
        print("proto unknown")
        return
    check = 10  # python 似乎能够正确填充校验和
    saddr = socket.inet_aton ( src )  # 如果需要，可以使用欺骗源 IP 地址
    daddr = socket.inet_aton ( dst )

    # 将 ihl 字段和 version 字段(左移 4 bits)拼接在一起
    ihl_version = (version << 4) + ihl

    # 包格式字符串中的 ! 表示网络顺序
    ip_header = struct.pack('!BBHHHBBH4s4s' , ihl_version, tos, tot_len, id, frag_off, ttl, proto, check, saddr, daddr)
    return ip_header

def tcp_header(src,dst,sport,dport):

    ''' TCP 报头 '''
    # TCP 报头的各个字段
    source = sport    # 源端口号
    dest = dport      # 目的端口号
    seq = 0
    ack_seq = 0
    # doff 用于标识该 TCP 报头有多少个 32bits（即 4 字节）。
    # 因为 4bits 最大能标识 15，所以 TCP 头部最长是60字节。本例中为 5 * 4 = 20 bytes
    doff = 5    
    # TCP 的标志位
    fin = 0
    syn = 1
    rst = 0
    psh = 0
    ack = 0
    urg = 0
    window = socket.htons (5840)    #  所允许的最大窗口大小
    check = 0
    urg_ptr = 0

    offset_res = (doff << 4) + 0
    tcp_flags = fin + (syn << 1) + (rst << 2) + (psh <<3) + (ack << 4) + (urg << 5)

    # 包格式字符串中的 ! 表示网络顺序, 此时是根据上述生成的字段来构造一个 TCP 报头(其为一个 bytes 对象)
    tcp_header = struct.pack('!HHLLBBHHH', source, dest, seq, ack_seq, offset_res, tcp_flags, window, check, urg_ptr)

    # 伪报头字段
    source_address = socket.inet_aton(src)
    dest_address = socket.inet_aton(dst)
    placeholder = 0
    proto = socket.IPPROTO_TCP
    tcp_length = len(tcp_header)

    psh = struct.pack('!4s4sBBH', source_address , dest_address , placeholder , proto , tcp_length)
    psh = psh + tcp_header
    
    # 根据重新新的 psh 来重新计算出正确的校验和并用于后面的填充
    tcp_checksum = checksum(psh)

    # 再次制作 TCP 报头并填写正确的校验和
    tcp_header = struct.pack('!HHLLBBHHH', source, dest, seq, ack_seq, offset_res, tcp_flags, window, tcp_checksum, urg_ptr)

    # 最终完整数据包 - 即一个没有任何数据的 SYN 数据包
    return tcp_header

def udp_header(sport,dport):

    ''' UDP 报头 '''

    sport = sport     # 任意的源端口号
    dport = dport     # 任意的目的端口号
    length = 8
    checksum = 0
    header = struct.pack('!HHHH', sport, dport, length, checksum)

    return header

def getInterfaceName():

    ''' 判断端口号中是否含有 eth0 端口 '''

    # 假设其含有 eth0 端口
    return [x for x in os.listdir('/sys/cla'
                                  'ss/net') if "eth0" in x][0]

def getICMPInfo(data):
    
    ''' 获取 ICMP 数据包的多个信息 '''

    # 我们假设它总是一个 ICMP 数据包

    # 对数据包中的 ICMP 报头进行解析
    icmp_pkt = icmphdr.disassemble(data[20:28])

    # 检查其类型是否为 3 或 11
    # type 3 = 目的地不可达(又可分为多种类型, 如主机不可达、协议不可达、端口不可达等)
    # type 11 = 生存时间 (TTL) 超时/过期
    if icmp_pkt.type != 11 and icmp_pkt.type != 3:
        return -1,-1,-1,-1

    # 对引用的 IP 报头(即 data[28:48] )进行解析
    ref_ip_pkt = iphdr.disassemble(data[28:48])

    if ref_ip_pkt.tos != 128:
        return -1, -1, -1,-1

    original_header, id = bool(ref_ip_pkt.id & (1<<15)), ref_ip_pkt.id & 0x7fff

    # 传输层协议为 TCP
    if ref_ip_pkt.proto == 6:
        # 我们仅解析 TCP 报头的前 8 个字节
        ref_tcp_pkt = tcphdr.disassemble(data[48:56])
        return (ref_ip_pkt.src, ref_ip_pkt.dst, "TCP"), id, (ref_tcp_pkt.sport, ref_tcp_pkt.dport), original_header
    
    # 传输层协议为 UDP
    elif ref_ip_pkt.proto == 17:
        # 我们仅解析 UDP 报头的前 8 个字节
        ref_udp_pkt = udphdr.disassemble(data[48:56])
        return (ref_ip_pkt.src, ref_ip_pkt.dst, "UDP"), id, (ref_udp_pkt.sport, ref_udp_pkt.dport), original_header

    else:
        return -1,-1,-1,-1

def getPortsICMP(data, id):

    ''' 获取 ICMP 数据包所包含的端口号的信息 '''
    # 我们假设它总是一个 ICMP 数据包

    icmp_pkt = icmphdr.disassemble(data[20:28])
    # 检查其类型是否为 3 或 11
    # type 3 = 目的地不可达(又可分为多种类型, 如主机不可达、协议不可达、端口不可达等)
    # type 11 = 生存时间 (TTL) 超时/过期
    if icmp_pkt.type != 11 and icmp_pkt.type != 3:
        return -1

    # 对引用的 IP 报头(即 data[28:48] )进行解析
    ref_ip_pkt = iphdr.disassemble(data[28:48])

    # 检查 IP 报头的 id 是否一致
    if ref_ip_pkt.id != id:
        return -1

    # 传输层协议为 TCP
    if ref_ip_pkt.proto == 6:
        # 仅解析 TCP 报头的前 8 个字节
        ref_tcp_pkt = tcphdr.disassemble(data[48:56])
        # 仅返回 (sport, dport) 这个元组
        return (ref_tcp_pkt.sport, ref_tcp_pkt.dport)
    
    # 传输层协议为 UDP
    elif ref_ip_pkt.proto == 17:
        # 仅解析 UDP 报头的前 8 个字节
        ref_udp_pkt = udphdr.disassemble(data[48:56])
        # 仅返回 (sport, dport) 这个元组
        return (ref_udp_pkt.sport, ref_udp_pkt.dport)

    else:
        return -1


def check_valid_icmp(src,dst,sport,dport,proto,data):

    # 获取 IP 报头
    ip_pkt = iphdr.disassemble(data[:20])

    # 检查 IP 报头的 proto 字段是否为 ICMP 所对应的值
    if ip_pkt.proto != socket.IPPROTO_ICMP:
        return False

    # 从数据包中解析出 ICMP 报头
    icmp_pkt = icmphdr.disassemble(data[20:28])

    # 检查其类型是否为 3 或 11
    # type 3 = 目的地不可达(又可分为多种类型, 如主机不可达、协议不可达、端口不可达等)
    # type 11 = 生存时间 (TTL) 超时/过期
    if icmp_pkt.type != 11 and icmp_pkt.type != 3:
        return False

    # 获取引用的 IP 报头
    ref_ip_pkt = iphdr.disassemble(data[28:48])

    # 现在我们检查 src, dst 和 protocol
    if ref_ip_pkt.src != src or ref_ip_pkt.dst != dst or ref_ip_pkt.proto != proto:
        return False

    # 现在我们以不同的方式检查它是 TCP 还是 UDP
    # 检查传输层协议是否为 TCP
    if ref_ip_pkt.proto == 6:

        ref_tcp_pkt = tcphdr.disassemble(data[48:56])
        # 现在我们继续检查端口
        if ref_tcp_pkt.sport != sport or ref_tcp_pkt.dport != dport:
            return False
        
    # 检查传输层协议是否为 UDP
    elif ref_ip_pkt.proto == 17:
        
        ref_udp_pkt = udphdr.disassemble(data[48:56])
        # 现在我们继续检查端口
        if ref_udp_pkt.sport != sport or ref_udp_pkt.dport != dport:
            return False
        
    else:
        return False

    return True

def traceroute(src=None, dst=None, sport=5001, dport=5002):

    """
    Traceroute 查找从 src 到 dst 的路径上的 ip, 但是它需要跳数(hops)才能工作, 否则它不知道何时停止。
    必须这样做才能实现快速执行, 因此我们不必等到最后一个路由器或目的主机的回复。但是, 我们需要事先知道长度
    :param src:   源 IP
    :param dst:   目的 IP
    :param sport: 源端口号
    :param dport: 目的端口号
    :param proto: 
    :param hops:
    :param kwargs:
    :return:
    """

    # dest 可以是个 ip 地址或者域名
    dst =  socket.gethostbyname(dst)
    icmp = socket.getprotobyname('icmp')
    proto = socket.getprotobyname('tcp')
    src_port = sport
    dst_port = dport
    #TODO: I FIXED THIS BECAUSE I CAN NOT SOLVE IT..
    max_hops = 50

    # 如果 src 为 None, 我们可以通过获取端口号所对应的 IP 地址来充当源 IP 地址
    if src == None:
        interface_name = getInterfaceName()
        src = get_ip_address(interface_name)

    recv_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, icmp)
    recv_socket.settimeout(0.5)

    # 我们使用路由器接口 IPS 返回的路由，我们必须使用拓扑来获取该 IP 地址来自哪个路由器，因为它可能来自其任何接口
    route = []
    send_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, proto)

    # 告诉内核不要放入报头，因为我们正在提供它
    send_socket.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

    try:
        curr_addr = None
        # 生成一个 TCP 报头
        tcp_h = tcp_header(src, dst, src_port, dst_port)
        for ttl in range(1, max_hops):
            # 生成一个 IP 报头并将其与前面的 TCP 报头拼接在一起
            packet = ip_header(src, dst, ttl, "tcp") + tcp_h
            send_socket.sendto(packet, (dst, 0))

            try:
                # 获取数据直到它是一个有效的 ICMP 数据包
                data, curr_addr = recv_socket.recvfrom(512)
                while not check_valid_icmp(src, dst, sport, dport, proto, data):
                    data, curr_addr = recv_socket.recvfrom(512)

            except socket.error:
                # 如果已经超时，则我们返回
                return route

            # 如果我们执行到这里并且 curr_addr 为 None, 则意味着发生了超时
            # 如果 curr_addr 不为 None, 则我们将其添加到 route 列表中, 用来记录路由路径信息
            if curr_addr:
                curr_addr = curr_addr[0]

                route.append(curr_addr)
                curr_addr = None
        
        # 依次关闭两个套接字
        send_socket.close()
        recv_socket.close()
        return route

    finally:
        send_socket.close()
        recv_socket.close()
