#!/usr/bin/env python3
import argparse
import sys
import socket
import random
import struct

from scapy.all import sendp, get_if_list, get_if_hwaddr
from scapy.all import Ether, IP, UDP, TCP
import time

def get_if():
    ''' 查询并返回 eth0 接口 '''
    ifs=get_if_list()
    iface=None # "h1-eth0"
    for i in get_if_list():
        if "eth0" in i:
            iface=i
            break
    if not iface:
        print("Cannot find eth0 interface")
        exit(1)
    return iface

def main():

    # 参数: 目的 IP 地址, 随机发送的数据包的数量
    if len(sys.argv)<3:
        print('pass 2 arguments: <destination> <number_of_random_packets>')
        exit(1)

    addr = socket.gethostbyname(sys.argv[1])
    iface = get_if()

    print("在接口 %s 上向目的地 %s 发送数据包" % (iface, str(addr)))

    # 循环生成随机的数据包
    for _ in range(int(sys.argv[2])):

        pkt = Ether(src=get_if_hwaddr(iface), dst='ff:ff:ff:ff:ff:ff')
        # 目的端口号为7777, 源端口号随机
        pkt = pkt /IP(dst=addr) / TCP(dport=7777, sport=random.randint(2000,65535))
        # 在 iface 接口上发送 pkt 数据包
        sendp(pkt, iface=iface, verbose=False)
        time.sleep(0.1)

if __name__ == '__main__':
    main()
