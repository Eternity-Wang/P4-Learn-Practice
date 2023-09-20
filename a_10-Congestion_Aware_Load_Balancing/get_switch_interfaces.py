from p4utils.utils.helper import load_topo

topo = load_topo('topology.json')

for host in sorted(topo.get_hosts().keys(), key = lambda x: int(x[1:])):

    # 获取主机的第一个接口(其实也就是与交换机相连的那个接口) host_intf
    host_intf = topo.get_host_first_interface(host)
    # 根据主机和主机的接口获取交换机的名称 sw
    sw = topo.interface_to_node(host, host_intf)
    
    print(host, topo.get_intfs()[sw][host]['intfName'])