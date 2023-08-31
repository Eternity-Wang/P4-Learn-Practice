"""A central controller computing and installing shortest paths.

In case of a link failure, paths are recomputed.
"""

import os, random
from cli import CLI
import networkx as nx
from networkx.algorithms import all_pairs_dijkstra, all_pairs_dijkstra_path

from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI


class RerouteController(object):
    """ 快速重新路由中所用的控制器. """

    def __init__(self):
        """ 初始化拓扑和数据结构 """

        # 首先检查路径下是否存在topology.json文件
        if not os.path.exists('topology.json'):
            print("Could not find topology object!\n")
            raise Exception

        self.topo = load_topo('topology.json')
        self.controllers = {}
        self.classify_topo_nodes()
        self.connect_to_switches()
        self.reset_states()

        # 预先配置所有的 MAC 地址
        self.install_macs()

        # 按照下一跳索引并填充寄存器
        self.install_nexthop_indices()
        self.update_nexthops()

    def connect_to_switches(self):

        ''' 与拓扑中所有的交换机建立 thrift 连接 '''

        for p4switch in self.topo_p4switches:
            # 获取某个交换机的 thrift 端口号
            thrift_port = self.topo.get_thrift_port(p4switch)
            # 与该交换机建立 thrift 连接
            self.controllers[p4switch] = SimpleSwitchThriftAPI(thrift_port) 

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

        for control in self.controllers.values():
            control.reset_state()

    def install_macs(self):
        """ 为所有交换机安装 port-to-mac 的映射

        注意: 实际的交换机会依靠 L2 learning 来实现此功能
        """
        for switch, control in self.controllers.items():
            print("为交换机 '%s' 安装 MAC 地址的表项" % switch)
            print("=========================================\n")
            for neighbor in self.topo.get_neighbors(switch):
                mac = self.topo.node_to_node_mac(neighbor, switch)
                port = self.topo.node_to_node_port_num(switch, neighbor)
                control.table_add('rewrite_mac', 'rewriteMac',
                                  [str(port)], [str(mac)])

    def install_nexthop_indices(self):

        """ 为所有交换机安装从前缀到下一跳 ID 的映射 """

        for switch, control in self.controllers.items():
            print("为交换机 '%s' 安装下一跳索引的表项" % switch)
            print("===========================================\n")

            # 首先清空 ipv4_lpm 表
            control.table_clear('ipv4_lpm')
            for host in self.topo_hosts:
                subnet = self.get_host_net(host)
                index = self.get_nexthop_index(host)
                print("子网:", subnet, "索引:", index)
                control.table_add('ipv4_lpm', 'read_port',
                                  [subnet], [str(index)])

    def get_host_net(self, host):

        """ 返回一个主机的 IP 地址和子网

        参数:
            host (str): The host for which the net will be retruned.

        返回值:
            str: IP and subnet in the format "address/mask".
        """

        gateway = self.topo.get_host_gateway_name(host)
        return self.topo.get_intfs()[host][gateway]['ip']

    def get_nexthop_index(self, host):

        """ 返回某个目的地(主机)对应的下一跳索引

        参数:
            host (str): Name of destination node (host).

        返回值:
            int: nexthop index, used to look up nexthop ports.
        """

        # 给每个主机分配一个单独的索引号(用于对寄存器中存放的下一跳进行索引)
        host_list = sorted(self.topo_hosts)
        return host_list.index(host)

    def get_port(self, node, nexthop_node):

        """从节点的角度返回下一跳的出口端口

        参数:
            node (str): Name of node for which the port is determined.
            nexthop_node (str): Name of node to reach.

        返回值:
            int: nexthop port
        """

        return self.topo.node_to_node_port_num(node, nexthop_node)

    def failure_notification(self, failures):

        """ 如果某个链路出现故障时调用

        参数:
            failures (list(tuple(str, str))): List of failed links.
        """

        self.update_nexthops(failures=failures)

    # Helpers to update nexthops.
    # ===========================

    def dijkstra(self, failures=None):
        """ 计算最短路径和距离

        参数:
            failures (list(tuple(str, str))): List of failed links.

        返回值:
            tuple(dict, dict): First dict: distances, second: paths.
        """

        t_graph = nx.Graph()

        # 向创建的拓扑添加相应的节点信息
        t_graph.add_nodes_from(self.topo_hosts)
        t_graph.add_nodes_from(self.topo_p4switches)

        # 向创建的拓扑添加相应的边信息
        t_graph.add_edges_from(self.topo.edges())

        for u,v in t_graph.edges:
            get_weight = self.topo.get_edge_data(u, v)['weight']
            if get_weight != 0:
                t_graph.add_edge(u, v, weight=get_weight) 
        
        # 判断 failures 是否为 None
        if failures is not None:
            t_graph = t_graph.copy()
            # 将所有出现故障的链路从拓扑图中删除/移去
            for failure in failures:
                t_graph.remove_edge(*failure)
        
        dijkstra = dict(all_pairs_dijkstra(t_graph, weight="weight"))

        distances = {node: data[0] for node, data in dijkstra.items()}
        paths = {node: data[1] for node, data in dijkstra.items()}

        return distances, paths
    

    def compute_nexthops(self, failures=None):
        """ 计算所有交换机下的到每个主机的最佳下一跳。

        可选地, 可以将某些链路标记为故障。这样在计算最短路径时, 该链路将被移除。

        参数:
            failures (list(tuple(str, str))): List of failed links.

        返回值:
            dict(str, list(str, str, int))):
                Mapping from all switches to subnets, MAC, port.
        """

        # 获取各个节点到其他节点(包含主机和交换机)的最短路径
        all_shortest_paths = self.dijkstra(failures=failures)[1]

        # print("拓扑中的所有最短路径", all_shortest_paths)

        # 将最短路径转换为每个交换机到对应主机的下一跳节点的映射
        results = {}
        for switch in self.controllers:
            # switch_results 列表用于保存当前 switch 下
            # 各个主机与下一跳之间的元组
            switch_results = results[switch] = []
            for host in self.topo_hosts:
                try:
                    # 获取从 switch 到 host 的最短路径
                    path = all_shortest_paths[switch][host]
                except KeyError:
                    print("WARNING: The graph is not connected!")
                    print("'%s' cannot reach '%s'." % (switch, host))
                    continue
                # 将 path[1] 赋给 nexthop(下一跳), 因为 path[0] 即为 switch 自己
                nexthop = path[1]  
                # 这里便给出了 switch 到某个 host 的 nexthop 信息, 
                # 并作为元组进行存放 
                switch_results.append((host, nexthop))
        
        return results

    # 更新下一跳.
    # ================

    def update_nexthops(self, failures=None):

        """ 在所有交换机上安装下一跳 """

        # 首先计算出每个交换机到达对应主机的最佳下一跳
        nexthops = self.compute_nexthops(failures=failures)
        print("==============================")
        print("计算出的所有主要下一跳:\n", nexthops)

        # 根据下一跳信息和故障链路计算出 LFA (备用下一跳)
        lfas = self.compute_lfas(nexthops, failures=failures)
        print("==============================")
        print("计算出的所有备用下一跳:\n", lfas)

        # 从 nexthops 中依次取出 switch 和 destinations
        for switch, destinations in nexthops.items():
            print("===============================")
            print("为交换机 '%s' 更新下一跳" % switch)
            
            control = self.controllers[switch]
            # 再依次从 destinations 中取出 host 和 nexthop
            print("首先对交换机中主要下一跳的信息进行更新")
            for host, nexthop in destinations:
                # 返回 host 对应的 nexthop_id
                nexthop_id = self.get_nexthop_index(host)
                # 根据 nexthop 和当前 switch 获取对应的端口号
                port = self.get_port(switch, nexthop)
                # 将主要下一跳对应的端口号写入到 primaryNH 寄存器中
                control.register_write('primaryNH', nexthop_id, port)

        #######################################################################
        # 计算无环路备用下一跳并在下面安装它们。
        #######################################################################

            # LFA solution.
            # =============
            print("------------------")
            print("接着安装 LFAs 的信息")
            print("------------------")

            for host, nexthop in destinations:
                nexthop_id = self.get_nexthop_index(host)
                # 如果主机和下一跳是同一个的话
                if host == nexthop:
                    continue  # 如果主机所连的链路出现故障则无法执行任何操作.

                try:
                    # 查询是否存在 LFA 备份下一跳
                    lfa_nexthop = lfas[switch][host]
                except KeyError:
                    print("警告: 如果下一跳 %s 不可用的话! "% (nexthop) + \
                          "从 %s 到 %s 是没有 LFA 的" % (switch, host) )
                    lfa_nexthop = nexthop  # 此时需要回退到默认 nh.

                # 如果存在 LFA 备份下一跳, 则获取其(即某个交换机)
                # 与当前 switch 之间连接的端口号
                lfa_port = self.get_port(switch, lfa_nexthop)
                # 将备份下一跳对应的端口号写入到 alternativeNH 寄存器中
                control.register_write('alternativeNH', nexthop_id, lfa_port)


    def compute_lfas(self, nexthops, failures=None):

        """ 为所有下一跳计算 LFA (无环路备用) """

        # 获取某个节点到其他所有节点的路径权重信息
        _d = self.dijkstra(failures=failures)[0]

        print(_d)

        lfas = {}
        for switch, destinations in nexthops.items():
            switch_lfas = lfas[switch] = {}
            # 获取与 switch 连接的所有交换机的名称并存放在列表中
            connected = set(self.topo.get_switches_connected_to(switch))

            for host, nexthop in destinations:
                if nexthop == host:
                    continue  # 如果主机所连的链路出现故障则无法执行任何操作.

                # 将主要下一跳(即nexthop)从中移除
                # 接下来将从 others 里面计算出备用下一跳
                others = connected - {nexthop}
                
                # 检查备用下一跳是否无循环
                noloop = []
                for alternate in others:
                    # 必须遵循如下条件:
                    # D(N, D) < D(N, S) + D(S, D)
                    if (_d[alternate][host]
                            < _d[alternate][switch] + _d[switch][host]):
                        total_dist = _d[switch][alternate] + \
                            _d[alternate][host]
                        noloop.append((alternate, total_dist))

                    if not noloop:
                        continue  # No LFA :(

                    # 保持 LFA 距离始终为最短的
                    switch_lfas[host] = min(noloop, key=lambda x: x[1])[0]

        return lfas


if __name__ == "__main__":
    controller = RerouteController()  # pylint: disable=invalid-name
    CLI(controller)
