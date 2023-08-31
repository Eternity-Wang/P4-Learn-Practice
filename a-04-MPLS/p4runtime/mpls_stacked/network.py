from p4utils.mininetlib.network_API import NetworkAPI

net = NetworkAPI()

# Network general options
net.setLogLevel('info')
net.setCompiler(p4rt=True)
net.execScript('python controller.py', reboot=True)

# Network definition
net.addP4RuntimeSwitch('s1')
net.addP4RuntimeSwitch('s2')
net.addP4RuntimeSwitch('s3')
net.addP4RuntimeSwitch('s4')
net.addP4RuntimeSwitch('s5')
net.addP4RuntimeSwitch('s6')
net.addP4RuntimeSwitch('s7')
net.setP4SourceAll('stacked.p4')

net.addHost('h1')
net.addHost('h2')
net.addHost('h3')

net.addLink("h1", "s1", port2=1)
net.addLink("s1", "s2", port1=2, port2=1)
net.addLink("s1", "s3", port1=3, port2=1)
net.addLink("s2", "s4", port1=2, port2=1)
net.addLink("s3", "s4", port1=2, port2=2)
net.addLink("s4", "s5", port1=3, port2=1)
net.addLink("s4", "s6", port1=4, port2=1)
net.addLink("s5", "s7", port1=2, port2=1)
net.addLink("s6", "s7", port1=2, port2=2)
net.addLink("s7", "h2", port1=3)
net.addLink("s7", "h3", port1=4)

# Assignment strategy
net.l3()

# Nodes general options
net.enablePcapDumpAll()
net.enableLogAll()
net.enableCli()
net.startNetwork()