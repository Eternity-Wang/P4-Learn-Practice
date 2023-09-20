from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI

class RoutingController(object):

    def __init__(self):

        self.topo = load_topo('topology.json')
        self.controllers = {}
        self.init()

    def init(self):
        ''' 控制器的初始化程序(连接所有交换机,重置状态,设置表的默认值) '''

        self.classify_topo_nodes()
        self.connect_to_switches()
        self.reset_states()
        self.set_table_defaults()

    def classify_topo_nodes(self):
        " 对拓扑中的所有节点进行分类, 并存放到对应的列表中 "

        self.topo_hosts = []
        self.topo_p4switches = []

        # 获取 topo 中的所有节点(包括主机和交换机)
        topo_nodes = self.topo.get_nodes(fields=['device_id'])
        # 遍历 topo 中的所有节点, 并判断其为主机还是交换机
        for key in list(topo_nodes.keys()):
            if topo_nodes[key] == None:
                self.topo_hosts.append(key)
            else:
                self.topo_p4switches.append(key)
        
        print("拓扑中的主机有:", self.topo_hosts)
        print("拓扑中的P4交换机有:", self.topo_p4switches)

    def reset_states(self):
        """ 重置交换机的寄存器, 表等等 """

        [controller.reset_state() for controller in self.controllers.values()]

    def connect_to_switches(self):
        ''' 与拓扑中所有的交换机建立 thrift 连接 '''

        for p4switch in self.topo_p4switches:
            # 获取某个交换机的 thrift 端口号
            thrift_port = self.topo.get_thrift_port(p4switch)
            # 与该交换机建立 thrift 连接
            self.controllers[p4switch] = SimpleSwitchThriftAPI(thrift_port) 

    def set_table_defaults(self):
        ''' 将所有交换机的表的默认值进行设置 '''

        for controller in self.controllers.values():
            controller.table_set_default("ipv4_lpm", "drop", [])
            controller.table_set_default("ecmp_group_to_nhop", "drop", [])

    def add_mirroring_ids(self):
        ''' 添加镜像号和出口端口号(mirror_id, egress_port) '''

        for sw_name, controller in self.controllers.items():
            # 镜像ID为100, 出口端口号为1
            controller.mirroring_add(100, 1)

    def set_egress_type_table(self):
        ''' 设置表的出口类型(主机或是交换机)
            
            将某个端口号与其对应相连的节点类型进行绑定'''

        for sw_name, controller in self.controllers.items():

            # 循环遍历与 sw_name 交换机相连的所有邻居节点和对应的接口号
            for intf, node in self.topo.get_interfaces_to_node(sw_name).items():
                # 获取 sw_name 交换机的 intf 接口对应的端口号 
                port_number = self.topo.interface_to_port(sw_name, intf)

                # 判断邻居节点的类型: 主机为1, 交换机为2
                if self.topo.isHost(node):
                    node_type_num = 1
                elif self.topo.isP4Switch(node):
                    node_type_num = 2

                print("table_add at {}:".format(sw_name))
                # 添加表项
                self.controllers[sw_name].table_add("egress_type", "set_egress_type", [str(port_number)], [str(node_type_num)])


    def route(self):
        ''' 添加与路由转发相关的表项 '''

        switch_ecmp_groups = {sw_name:{} for sw_name in self.topo_p4switches}

        for sw_name, controller in self.controllers.items():
            # 循环遍历拓扑中所有的 P4 交换机
            for sw_dst in self.topo_p4switches:

                # 如果 sw_name 和 sw_dst 对应的是同一个交换机
                if sw_name == sw_dst:

                    # 循环遍历所有与 sw_name 交换机相连的主机
                    for host in self.topo.get_hosts_connected_to(sw_name):
                        # 获取与该主机相连的交换机的端口号
                        sw_port = self.topo.node_to_node_port_num(sw_name, host)
                        # 分别获取该主机的 IP 地址和 MAC 地址
                        host_ip = self.topo.get_host_ip(host) + "/32"
                        host_mac = self.topo.get_host_mac(host)

                        # 向 ipv4_lpm 添加条目用于设置下一跳
                        print("table_add at {}:".format(sw_name))
                        self.controllers[sw_name].table_add("ipv4_lpm", "set_nhop", [str(host_ip)], [str(host_mac), str(sw_port)])

                # 检查 sw_dst 交换机是否有直接相连的主机
                else:
                    if self.topo.get_hosts_connected_to(sw_dst):
                        # 获取 sw_name 和 sw_dst 之间的所有的最短路径列表 paths
                        paths = self.topo.get_shortest_paths_between_nodes(sw_name, sw_dst)

                        # 循环遍历所有与 sw_dst 交换机相连的主机
                        for host in self.topo.get_hosts_connected_to(sw_dst):

                            # 如果仅有一条最短路径
                            if len(paths) == 1:
                                # 获取第一条最短路径的下一跳节点 next_hop
                                next_hop = paths[0][1]

                                # 获取转发所用的信息
                                host_ip = self.topo.get_host_ip(host) + "/24"
                                sw_port = self.topo.node_to_node_port_num(sw_name, next_hop)
                                dst_sw_mac = self.topo.node_to_node_mac(next_hop, sw_name)

                                # 向 ipv4_lpm 表添加表项
                                # 匹配项: 主机的 IP 地址
                                # 输出参数: 目的交换机的 MAC 地址, 交换机的出口端口号
                                print("table_add at {}:".format(sw_name))
                                self.controllers[sw_name].table_add("ipv4_lpm", "set_nhop", [str(host_ip)],
                                                                    [str(dst_sw_mac), str(sw_port)])
                                
                            # 如果最短路径数量多于一条
                            elif len(paths) > 1:
                                # 依次取出每条最短路径的下一跳, 并存入 next_hops 列表中
                                next_hops = [x[1] for x in paths]
                                # 依次获取下一跳交换机的 MAC 地址和相应的出口端口号并存入到一个元组中
                                # list[tuple(dst_sw_mac, dst_sw_port)]
                                dst_macs_ports = [(self.topo.node_to_node_mac(next_hop, sw_name),
                                                   self.topo.node_to_node_port_num(sw_name, next_hop))
                                                  for next_hop in next_hops]
                                host_ip = self.topo.get_host_ip(host) + "/24"

                                # 检查 ECMP 组是否已经存在, ECMP 组是由所使用的下一个使用的端口数来定义，因此我们可以使用 dst_macs_ports 作为关键字。
                                if switch_ecmp_groups[sw_name].get(tuple(dst_macs_ports), None):
                                    ecmp_group_id = switch_ecmp_groups[sw_name].get(tuple(dst_macs_ports), None)
                                    print("table_add at {}:".format(sw_name))
                                    self.controllers[sw_name].table_add("ipv4_lpm", "ecmp_group", [str(host_ip)],
                                                                        [str(ecmp_group_id), str(len(dst_macs_ports))])

                                # 如果不存在则需要为此交换机新建一个 ECMP 组
                                else:
                                    # 分配一个新的 ECMP 组的 ID 号
                                    # ID 号, 即交换机已有的 ECMP 组的总数 + 1
                                    new_ecmp_group_id = len(switch_ecmp_groups[sw_name]) + 1

                                    # 将一组 (mac, port) 与新的 ECMP 组进行绑定
                                    switch_ecmp_groups[sw_name][tuple(dst_macs_ports)] = new_ecmp_group_id

                                    # 依次向 ECMP 组中的每个 (mac, port) 添加表项
                                    for i, (mac, port) in enumerate(dst_macs_ports):
                                        print("table_add at {}:".format(sw_name))
                                        self.controllers[sw_name].table_add("ecmp_group_to_nhop", "set_nhop",
                                                                            [str(new_ecmp_group_id), str(i)],
                                                                            [str(mac), str(port)])

                                    # 添加转发规则
                                    print("table_add at {}:".format(sw_name))
                                    self.controllers[sw_name].table_add("ipv4_lpm", "ecmp_group", [str(host_ip)],
                                                                        [str(new_ecmp_group_id), str(len(dst_macs_ports))])


    def main(self):
        self.set_egress_type_table()
        self.add_mirroring_ids()
        self.route()


if __name__ == "__main__":
    controller = RoutingController().main()
