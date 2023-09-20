import sys
import random
import time
from p4utils.utils.helper import load_topo
from subprocess import Popen

topo = load_topo('topology.json')

iperf_send = "mx {0} iperf3 -c {1} -M 9000 -t {2} --bind {3} --cport {4} -p {5} 2>&1 >/dev/null"
iperf_recv = "mx {0} iperf3 -s -p {1} --one-off 2>&1 >/dev/null"

# 关闭已运行的 iperf 和 iperf3 进程
Popen("sudo killall iperf iperf3", shell=True)

# 随机生成两个目的端口号
port1 = random.randint(1024, 65000)
port2 = random.randint(1024, 65000)

# 将信息输入并分别为 h3 和 h4 启动两个接收器 receiver
Popen(iperf_recv.format("h3", port1), shell=True)
Popen(iperf_recv.format("h4", port2), shell=True)

time.sleep(1)

import sys
duration = int(sys.argv[1])

# 将信息输入并分别为 h1 和 h2 启动发送器 sender
# h1 -> h3 和 h2 -> h4 (src -> dst)
Popen(iperf_send.format("h1", topo.get_host_ip("h3"), duration, topo.get_host_ip("h1"), port1, port1), shell=True)
Popen(iperf_send.format("h2", topo.get_host_ip("h4"), duration, topo.get_host_ip("h2"), port2, port2), shell=True)

