from p4utils.mininetlib.network_API import NetworkAPI

net = NetworkAPI()

# 网络通用选项设置
net.setLogLevel('info')

# 网络中各组件的定义
net.addP4Switch('s1')
net.addP4Switch('s2')
net.addP4Switch('s3')
net.setP4SourceAll('rsvp.p4')

net.addHost('h1')
net.addHost('h2')
net.addHost('h3')
net.addHost('h4')
net.addHost('h5')
net.addHost('h6')

net.addLink("h1", "s1")
net.addLink("h2", "s1")
net.addLink("s1", "s2")
net.addLink("s1", "s3")
net.addLink("s2", "s3")
net.addLink("h3", "s2")
net.addLink("h4", "s2")
net.addLink("h5", "s3")
net.addLink("h6", "s3")
net.setBwAll(10)

# 分配策略
net.l3()

# 节点通用选项设置
net.disablePcapDumpAll()
net.enableLogAll()
net.enableCli()
net.startNetwork()