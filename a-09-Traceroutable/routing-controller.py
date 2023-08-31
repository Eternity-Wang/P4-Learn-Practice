from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI

class RoutingController(object):

    def __init__(self):

        self.topo = load_topo('topology.json')
        self.controllers = {}
        self.init()

    def init(self):
        self.connect_to_switches()
        self.reset_states()
        self.set_table_defaults()

    def reset_states(self):

        ''' 重置交换机的寄存器, 表等等 '''

        [controller.reset_state() for controller in self.controllers.values()]

    def connect_to_switches(self):

        ''' 与拓扑中所有的交换机建立 thrift 连接 '''

        # 获取 topo 中的所有节点(包括主机和交换机)
        topo_nodes = self.topo.get_nodes(fields=['device_id'])
        # 删除 topo_nodes 字典中 key 为主机(如h1、h2等)的键值对
        for key in list(topo_nodes.keys()):
            if topo_nodes[key] == None:
                del topo_nodes[key]
        # 处理后生成一个只包含拓扑中的P4交换机的列表
        self.p4switches = list(topo_nodes.keys())
        print("拓扑中的P4交换机有:", self.p4switches)
        for p4switch in self.p4switches:
            # 获取某个交换机的 thrift 端口号
            thrift_port = self.topo.get_thrift_port(p4switch)
            # 与该交换机建立 thrift 连接
            self.controllers[p4switch] = SimpleSwitchThriftAPI(thrift_port)

    def set_table_defaults(self):

        ''' 设置交换机中的每个表的默认动作(default action) '''
        for controller in self.controllers.values():
            controller.table_set_default("ipv4_lpm", "drop", [])
            controller.table_set_default("ecmp_group_to_nhop", "drop", [])

    def set_icmp_ingress_port_table(self):

        for sw_name, controller in self.controllers.items():
            for intf, node in self.topo.get_interfaces_to_node(sw_name).items():
                print("链路相关信息为:", sw_name, intf, node)
                # 在本例中, node_to_node_interface_ip 函数中第一个参数最好为主机的名称, 
                # 第二个参数为交换机的名称. 这样才能够返回正确的 IP 地址.
                print(self.topo.node_to_node_interface_ip(node, sw_name))
                print(self.topo.node_interface_ip(sw_name, intf))
                ip = self.topo.node_to_node_interface_ip(node, sw_name).split("/")[0]
                port_number = self.topo.interface_to_port(sw_name, intf)

                print("table_add at {}:".format(sw_name))
                self.controllers[sw_name].table_add("icmp_ingress_port", "set_src_icmp_ip", [str(port_number)], [str(ip)])

    def route(self):

        switch_ecmp_groups = {sw_name:{} for sw_name in self.p4switches}
        print("交换机 ecmp 组", switch_ecmp_groups)

        for sw_name, controller in self.controllers.items():
            for sw_dst in self.topo.get_p4switches():

                #if its ourselves we create direct connections
                # 如果是我们自己，我们会建立直接联系
                if sw_name == sw_dst:
                    for host in self.topo.get_hosts_connected_to(sw_name):
                        sw_port = self.topo.node_to_node_port_num(sw_name, host)
                        host_ip = self.topo.get_host_ip(host) + "/32"
                        host_mac = self.topo.get_host_mac(host)

                        #add rule
                        print("table_add at {}:".format(sw_name))
                        self.controllers[sw_name].table_add("ipv4_lpm", "set_nhop", [str(host_ip)], [str(host_mac), str(sw_port)])

                # 检查是否有直接相连的主机
                else:
                    if self.topo.get_hosts_connected_to(sw_dst):
                        # 获取 sw_name 和 sw_dst 这两个节点之间的最短路径
                        paths = self.topo.get_shortest_paths_between_nodes(sw_name, sw_dst)
                        # 获取连接到 sw_dst 上的所有主机
                        for host in self.topo.get_hosts_connected_to(sw_dst):
                            
                            # 如果 paths 长度为 1
                            if len(paths) == 1:
                                next_hop = paths[0][1]

                                # 获取主机的 IP 地址并附加上子网掩码/前缀长度
                                host_ip = self.topo.get_host_ip(host) + "/24"
                                # 
                                sw_port = self.topo.node_to_node_port_num(sw_name, next_hop)
                                dst_sw_mac = self.topo.node_to_node_mac(next_hop, sw_name)

                                #add rule
                                # 添加
                                print("table_add at {}:".format(sw_name))
                                self.controllers[sw_name].table_add("ipv4_lpm", "set_nhop", [str(host_ip)],
                                                                    [str(dst_sw_mac), str(sw_port)])

                            elif len(paths) > 1:
                                next_hops = [x[1] for x in paths]
                                dst_macs_ports = [(self.topo.node_to_node_mac(next_hop, sw_name),
                                                   self.topo.node_to_node_port_num(sw_name, next_hop))
                                                  for next_hop in next_hops]
                                host_ip = self.topo.get_host_ip(host) + "/24"

                                #check if the ecmp group already exists. The ecmp group is defined by the number of next
                                #ports used, thus we can use dst_macs_ports as key
                                if switch_ecmp_groups[sw_name].get(tuple(dst_macs_ports), None):
                                    ecmp_group_id = switch_ecmp_groups[sw_name].get(tuple(dst_macs_ports), None)
                                    print("table_add at {}:".format(sw_name))
                                    self.controllers[sw_name].table_add("ipv4_lpm", "ecmp_group", [str(host_ip)],
                                                                        [str(ecmp_group_id), str(len(dst_macs_ports))])

                                #new ecmp group for this switch
                                else:
                                    new_ecmp_group_id = len(switch_ecmp_groups[sw_name]) + 1
                                    switch_ecmp_groups[sw_name][tuple(dst_macs_ports)] = new_ecmp_group_id

                                    #add group
                                    for i, (mac, port) in enumerate(dst_macs_ports):
                                        print("table_add at {}:".format(sw_name))
                                        self.controllers[sw_name].table_add("ecmp_group_to_nhop", "set_nhop",
                                                                            [str(new_ecmp_group_id), str(i)],
                                                                            [str(mac), str(port)])

                                    #add forwarding rule
                                    print("table_add at {}:".format(sw_name))
                                    self.controllers[sw_name].table_add("ipv4_lpm", "ecmp_group", [str(host_ip)],
                                                                        [str(new_ecmp_group_id), str(len(dst_macs_ports))])

    def main(self):
        self.set_icmp_ingress_port_table()
        self.route()


if __name__ == "__main__":
    controller = RoutingController().main()
