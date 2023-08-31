#!/usr/bin/env python3
import socket
import random
import os
import struct
import fcntl
import time
import pickle
import codecs

def checksum(msg):
    ''' 用于计算校验和 '''
    s = 0
    # loop taking 2 characters at a time
    for i in range(0, len(msg), 2):
        w = (msg[i] << 8) + msg[i+1]
        s = s + w

    s = (s>>16) + (s & 0xffff)
    #s = s + (s >> 16)    #complement and mask to 4 byte short
    s = ~s & 0xffff

    return s

def get_ip_address(ifname):
    ''' 获取IP地址 '''
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])


def eth_header(src, dst, proto=0x0800):
    src_bytes = b"".join([codecs.decode(x,'hex') for x in src.split(":")])
    dst_bytes = b"".join([codecs.decode(x,'hex') for x in dst.split(":")])
    return src_bytes + dst_bytes + struct.pack("!H", proto)

def ip_header(src,dst,ttl,proto,id=0):
    ''' 生成IP报头 '''
    # now start constructing the packet
    packet = ''
    # ip header fields
    ihl = 5
    version = 4
    tos = 128
    tot_len = 20 + 20   # python seems to correctly fill the total length, dont know how ??
    frag_off = 0
    if proto == "tcp":
        proto = socket.IPPROTO_TCP
    elif proto == "udp":
        proto = socket.IPPROTO_UDP
    else:
        print("proto unknown")
        return
    check = 10  # python seems to correctly fill the checksum
    saddr = socket.inet_aton ( src )  #Spoof the source ip address if you want to
    daddr = socket.inet_aton ( dst )

    ihl_version = (version << 4) + ihl

    # the ! in the pack format string means network order
    ip_header = struct.pack('!BBHHHBBH4s4s' , ihl_version, tos, tot_len, id, frag_off, ttl, proto, check, saddr, daddr)
    return ip_header

def tcp_header(src,dst,sport,dport):
    ''' 生成TCP报头 '''
    # tcp header fields
    source = sport #sourceport
    dest = dport  # destination port
    seq = 0
    ack_seq = 0
    doff = 5    #4 bit field, size of tcp header, 5 * 4 = 20 bytes
    #tcp flags
    fin = 0
    syn = 1
    rst = 0
    psh = 0
    ack = 0
    urg = 0
    window = socket.htons (5840)    #   maximum allowed window size
    check = 0
    urg_ptr = 0

    offset_res = (doff << 4) + 0
    tcp_flags = fin + (syn << 1) + (rst << 2) + (psh <<3) + (ack << 4) + (urg << 5)

    # the ! in the pack format string means network order
    tcp_header = struct.pack('!HHLLBBHHH' , source, dest, seq, ack_seq, offset_res, tcp_flags,  window, check, urg_ptr)

    # pseudo header fields
    source_address = socket.inet_aton( src )
    dest_address = socket.inet_aton(dst)
    placeholder = 0
    proto = socket.IPPROTO_TCP
    tcp_length = len(tcp_header)

    psh = struct.pack('!4s4sBBH' , source_address , dest_address , placeholder , proto , tcp_length)
    psh = psh + tcp_header

    tcp_checksum = checksum(psh)

    # make the tcp header again and fill the correct checksum
    tcp_header = struct.pack('!HHLLBBHHH' , source, dest, seq, ack_seq, offset_res, tcp_flags,  window, tcp_checksum , urg_ptr)

    # final full packet - syn packets dont have any data
    return tcp_header

def getInterfaceName():
    ''' 获取网卡接口的名称 '''
    #assume it has eth0

    return [x for x in os.listdir('/sys/cla'
                                  'ss/net') if "eth0" in x][0]

def send_n(s, packet, n):
    ''' 循环发送数据包(总数为n) '''
    for _ in range(n):
        s.send(packet)
        time.sleep(0.001)


def create_packet_ip_tcp(eth_h, src_ip, dst_ip, sport, dport):
    ''' 生成数据包(包含以太网报头、IP报头、TCP报头) '''
    return eth_h + ip_header(src_ip, dst_ip, 64, "tcp",1) + tcp_header(src_ip, dst_ip, sport, dport)

def get_random_flow():
    ''' 生成随机的流(主要生成随机的源ip, 目的ip, 源端口号, 目的端口号, 并返回) '''
    src_ip = socket.inet_ntoa(struct.pack("!I", random.randint(167772160, 4261412864)))
    dst_ip = socket.inet_ntoa(struct.pack("!I", random.randint(167772160, 4261412864)))
    sport = random.randint(1, 2 ** 16 - 2)
    dport = random.randint(1, 2 ** 16 - 2)
    return (src_ip, dst_ip, sport, dport)

def generate_test(n_packets, n_heavy_hitters, n_normal_flows, percentage_n_heavy_hitters=0.9):

    normal_flows = {}
    heavy_hitters = {}

    # 生成重击流
    for _ in range(n_heavy_hitters):
        flow = get_random_flow()
        # 检查生成的流是否已经存在于heavy_hitters字典中了
        # 如果存在则需要重新生成
        while flow in heavy_hitters:
            flow = get_random_flow()
        # 将此流的计数值置为0
        heavy_hitters[flow] = 0

    # 生成正常流(即小流)
    for _ in range(n_normal_flows):
        flow = get_random_flow()
        # 检查生成的流是否已经存在于heavy_hitters或normal_flows字典中了
        # 如果存在则需要重新生成
        while (flow in heavy_hitters or flow in normal_flows):
            flow = get_random_flow()
        # 将此流的计数值置为0
        normal_flows[flow] = 0

    for _ in range(n_packets):
        p = random.uniform(0,1)

        # 增加重击流的计数值
        if p <= percentage_n_heavy_hitters:
            flow = random.choice(list(heavy_hitters.keys()))
            heavy_hitters[flow] +=1

        # 增加正常流的计数值
        else:
            flow = random.choice(list(normal_flows.keys()))
            normal_flows[flow] +=1

    return heavy_hitters, normal_flows

def save_flows(flows):
    ''' 将发送的流及其相关信息写入到sent_flows.pickle这个文件中 '''
    with open("sent_flows.pickle", "wb") as f:
        pickle.dump(flows, f)

def main(n_packets, n_heavy_hitters, n_small_flows, p_heavy_hitter):

    send_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
    intf_name = getInterfaceName()
    send_socket.bind((intf_name, 0))

    eth_h = eth_header("01:02:20:aa:33:aa", "02:02:20:aa:33:aa", 0x800)
    heavy_hitters, small_flows = generate_test(n_packets, n_heavy_hitters, n_small_flows, p_heavy_hitter)

    # 将这两个字典进行融合(把small_flows字典中的键值对添加到heavy_hitters字典中)
    heavy_hitters.update(small_flows)
    # 将heavy_hitters字典的键值对信息拷贝到flows字典中
    flows = heavy_hitters.copy()

    # 将流的相关信息存入到对应的文件中，以便后面的控制器进行比较
    save_flows(flows)

    # 为每个流生成数据包并循环发送
    for flow, n in flows.items():
        packet = create_packet_ip_tcp(eth_h, *flow)
        send_n(send_socket, packet, n)

    send_socket.close()


if __name__ == "__main__":

    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument('--n-pkt', help='数据包的数量', type=int, required=False, default=5000)
    parser.add_argument('--n-hh', help='重击流的数量', type=int, required=False, default=10)
    parser.add_argument('--n-sfw', help='小流的数量', type=int, required=False, default=990)
    parser.add_argument('--p-hh', help='由重击流发送的数据包所占的百分比',type=float, required=False, default=0.95)
    args= parser.parse_args()

    main(args.n_pkt, args.n_hh, args.n_sfw, args.p_hh)


