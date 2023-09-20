#!/usr/bin/env python3
import sys
import os

from scapy.all import sniff, get_if_list, Ether, get_if_hwaddr, IP, Raw, Packet, BitField, bind_layers

def get_if():
    ''' 查询并返回 eth0 接口 '''
    iface=None
    for i in get_if_list():
        if "eth0" in i:
            iface=i
            break
    if not iface:
        print("Cannot find eth0 interface")
        exit(1)
    return iface

class Telemetry(Packet):
   ''' 遥测报头的定义(共两个字段, enq_depth和nextHeaderType) '''
   fields_desc = [ BitField("enq_depth", 0, 16),
                   #BitField("deq_depth", 0, 16),
                   BitField("nextHeaderType", 0, 16)]

def isNotOutgoing(my_mac):
    my_mac = my_mac
    def _isNotOutgoing(pkt):
        return pkt[Ether].src != my_mac

    return _isNotOutgoing

def handle_pkt(pkt):
    ''' 对数据包进行处理 '''

    # 获取 Ether 层的数据
    ether = pkt.getlayer(Ether)

    # 获取 Telemetry 层的数据
    telemetry = pkt.getlayer(Telemetry)
    # 打印获取到的队列信息
    print("Queue Info:")
    print("enq_depth", telemetry.enq_depth)
    #print "deq_depth", telemetry.deq_depth
    print()

# 表示两个层之间的前后关系: Ether -> Telemetry
bind_layers(Ether, Telemetry, type=0x7777)


def main():
    ifaces = [i for i in os.listdir('/sys/class/net/') if 'eth' in i]
    iface = ifaces[0]
    print("sniffing on %s" % iface)
    sys.stdout.flush()

    my_filter = isNotOutgoing(get_if_hwaddr(get_if()))

    sniff(filter="ether proto 0x7777", iface = iface,
          prn = lambda x: handle_pkt(x), lfilter=my_filter)

if __name__ == '__main__':
    main()