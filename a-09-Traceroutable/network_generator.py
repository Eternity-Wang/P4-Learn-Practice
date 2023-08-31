import argparse
import networkx

def init_python(f):
    
    ''' network.py文件的初始化部分代码的编写 '''

    f.write('from p4utils.mininetlib.network_API import NetworkAPI\n')
    f.write('\n')
    f.write('# Network general options\n')
    f.write('net = NetworkAPI()\n')
    f.write('net.setLogLevel("info")\n')

def end_python(f):

    ''' network.py文件的结尾部分代码的编写 '''

    f.write('\n')
    f.write('# Assignment strategy\n')
    f.write('net.l3()\n')
    f.write('\n')
    f.write('# Nodes general options\n')
    f.write('net.enablePcapDumpAll()\n')
    f.write('net.enableLogAll()\n')
    f.write('net.enableCli()\n')
    f.write('net.startNetwork()\n')

def create_linear_topo(f, num_switches):

    ''' 用于创建一个线性拓扑 '''
    
    f.write('\n')
    f.write('# Network definition\n')

    # 添加 num_switches 个交换机，编号从 1 到 num_switches
    for i in range(1, num_switches+1):
        f.write('net.addP4Switch("s{}")\n'.format(i))
    
    # 将 traceroutable.p4 程序加载到所有的交换机上
    f.write('net.setP4SourceAll("p4src/traceroutable.p4")\n')
    f.write('\n')

    # 添加 num_switches 个主机，编号从 1 到 num_switches
    for i in range(1, num_switches+1):
        f.write('net.addHost("h{}")\n'.format(i))

    f.write('\n')

    # 将这些主机依次连接到交换机上，例 h1 <-> s1，h2 <-> s2
    for i in range(1, num_switches+1):
        f.write('net.addLink("h{}", "s{}")\n'.format(i, i))

    # 将所有的交换机依次连接起来，即 s1 <-> s2 <-> s3 ....
    for i in range(1, num_switches):
        f.write('net.addLink("s{}", "s{}")\n'.format(i, i+1))

def create_circular_topo(f, num_switches):

    ''' 用于创建一个环形/圆形拓扑 '''

    # 首先创建一个线性拓扑
    create_linear_topo(num_switches)
    # 将 s1 和 sN 进行连接(添加一条链路)
    f.write('net.addLink("s{}", "s{}")\n'.format(1, num_switches))

def create_random_topo(f, degree=4, num_switches=10):

    ''' 用于创建一个随机拓扑 '''

    f.write('\n')
    f.write('# Network definition\n')

    g = networkx.random_regular_graph(degree, num_switches)
    trials = 0
    while not networkx.is_connected(g):
        g = networkx.random_regular_graph(degree, num_switches)
        trials +=1
        if trials >= 10:
            print("Could not Create a connected graph")
            return

    # 添加 num_switches 个交换机，编号从 1 到 num_switches
    for i in range(1, num_switches+1):
        f.write('net.addP4Switch("s{}")\n'.format(i))
    
    f.write('net.setP4SourceAll("p4src/traceroutable.p4")\n')
    f.write('\n')

    # 添加 num_switches 个主机，编号从 1 到 num_switches
    for i in range(1, num_switches+1):
        f.write('net.addHost("h{}")\n'.format(i))

    f.write('\n')

    # 将这些主机依次连接到交换机上，例 h1 <-> s1，h2 <-> s2
    for i in range(1, num_switches + 1):
        f.write('net.addLink("h{}","s{}")\n'.format(i, i))

    # 将这些交换机依次连接起来(这时根据边的随机性决定)
    for edge in g.edges:
        f.write('net.addLink("s{}","s{}")\n'.format(edge[0]+1, edge[1]+1))


def main():
    pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    # 输出 py 文件的名字
    parser.add_argument('--output_name', type=str, required=False, default="network_test.py")
    # 拓扑的类型, 默认为线性
    parser.add_argument("--topo", type=str, default="linear")
    # 交换机的数量, 默认为 2 个
    parser.add_argument('-n', type=str, required=False, default=2)
    # 节点的度数, 默认为 4 个
    parser.add_argument('-d', type=str, required=False, default=4)
    args = parser.parse_args()

    with open(args.output_name, 'w') as f:
        init_python(f)
        if args.topo == "linear":
            create_linear_topo(f, int(args.n))
        elif args.topo == "circular":
            create_circular_topo(f, int(args.n))
        elif args.topo == "random":
            create_random_topo(f, int(args.d), int(args.n))
        end_python(f)
