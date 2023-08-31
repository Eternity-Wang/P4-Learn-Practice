#!/usr/bin/env python3
import argparse
import sys
import socket
import random
import struct

from scapy.all import sendp, get_if_list, get_if_hwaddr
from scapy.all import Ether, IP, UDP, TCP

def get_if():
    ''' 获取并返回 eth0 接口的信息 '''
    ifs=get_if_list()
    iface=None 
    for i in get_if_list():
        if "eth0" in i:
            iface=i
            break
    if not iface:
        print("Cannot find eth0 interface")
        exit(1)
    return iface

def main():

    if len(sys.argv)<3:
        print('pass 2 arguments: <destination> <number_of_random_packets>')
        exit(1)
    
    # 获取目的地所对应的 IP 地址
    addr = socket.gethostbyname(sys.argv[1])
    # 获取主机的端口号
    iface = get_if()

    print("sending on interface %s to %s" % (iface, str(addr)))

    # 根据输入的 number_of_random_packets 这个参数来生成随机数量的数据包
    for _ in range(int(sys.argv[2])):
        # 构建 Ether 层
        pkt = Ether(src=get_if_hwaddr(iface), dst='ff:ff:ff:ff:ff:ff')
        # 构建 IP 层和 TCP 层并将其与 Ether 层进行拼接 (源端口号和目的端口号均为随机生成)
        pkt = pkt /IP(dst=addr) / TCP(dport=random.randint(5000,60000), sport=random.randint(49152,65535))
        sendp(pkt, iface=iface, verbose=False)

if __name__ == '__main__':
    main()
