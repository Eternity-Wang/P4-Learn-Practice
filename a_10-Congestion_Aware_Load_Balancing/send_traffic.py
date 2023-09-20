import sys
import random
import time
from p4utils.utils.helper import load_topo
from subprocess import Popen

topo = load_topo('topology.json')

# 从拓扑中筛选出所有主机的信息
topo_hosts = []
# 获取 topo 中的所有节点(包括主机和交换机)
topo_nodes = topo.get_nodes(fields=['device_id'])
# 遍历 topo 中的所有节点, 并判断其为主机还是交换机
for key in list(topo_nodes.keys()):
    if topo_nodes[key] == None:
        topo_hosts.append(key)       
print("拓扑中的主机有:", topo_hosts)

# ipef 对应的发送和接收的命令
iperf_send = "mx {0} iperf3 -M 9000 -c {1} -t {2} --bind {3} --cport {4} -p {5} 2>&1 >/dev/null"
iperf_recv = "mx {0} iperf3 -s -p {1} --one-off 2>&1 > /dev/null"

# 发送持续的时间间隔
duration = int(sys.argv[1])

send_cmds = []
recv_cmds = []

Popen("sudo killall iperf iperf3 > /dev/null", shell=True)

num_hosts = 8
num_senders= 4

for src_host in sorted(topo_hosts)[:num_senders]:
    dst_host = 'h' + str((int(src_host[1:]) + 3) % num_hosts + 1)

    # 分别随机生成源端口号和目的端口号
    src_port = random.randint(1025, 65000)
    dst_port = random.randint(1025, 65000)
    # 分别获取源主机和目的主机的 IP 地址
    src_ip = topo.get_host_ip(src_host)
    dst_ip = topo.get_host_ip(dst_host)
    
    # 分别向发送命令和接收命令填充相应的信息
    send_cmds.append(iperf_send.format(src_host, dst_ip, duration, src_ip, src_port, dst_port))
    recv_cmds.append(iperf_recv.format(dst_host, dst_port))

# 首先需要启动 receivers(接收器)
for recv_cmd in recv_cmds:
    Popen(recv_cmd, shell=True)

time.sleep(1)

# 然后启动 senders(发送器)
for send_cmd in send_cmds:
    Popen(send_cmd, shell=True)
