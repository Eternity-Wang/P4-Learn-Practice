import os
import threading
import time
from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI
from cli import RSVPCLI


class RSVPController(object):

    def __init__(self):
        """ 初始化拓扑和数据结构 """

        # 首先判断是否存在拓扑文件 topology.json
        if not os.path.exists('topology.json'):
            print('无法找到对应的拓扑对象!!!\n')
            raise Exception

        # 加载 topology.json
        self.topo = load_topo('topology.json')
        self.controllers = {}
        self.init()

        # 所有预留将按超时时间的顺序进行排序
        self.current_reservations = {}
        # 初始化链路的容量
        self.links_capacity = self.build_links_capacity()

        self.update_lock = threading.Lock()
        # 启动一个 timeout_thread 线程来判断已有的预留是否超时/过期
        self.timeout_thread = threading.Thread(target=self.reservations_timeout_thread, args=(1, ))
        # 将 timeout_thread 设置为守护线程
        self.timeout_thread.daemon = True
        self.timeout_thread.start()

    def init(self):
        """ 与所有交换机进行连接并重置这些交换机 """
        self.connect_to_switches() 
        self.reset_states()

    def reset_states(self):
        """ 重置交换机的寄存器, 表等等 """
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

    def build_links_capacity(self):
        """ 构建一个关于链路容量(键值对: (src, dst) -> bw )的字典(已实现)
        (键值对的数据类型, key: tuple -> value: float)

        返回值:
            dict: {edge: bw}
        """
        links_capacity = {}

        # 获取拓扑中各个交换机之间相连的所有链路
        self.topo_switches_links = self.topo.subgraph(self.p4switches).edges
        print("拓扑中各个交换机之间相连的所有链路:", self.topo_switches_links)
        
        # 对拓扑中由这些交换机所形成的所有的边进行迭代
        for src, dst in self.topo_switches_links:
            # 从拓扑中获取某条链路对应的带宽数据
            bw = self.topo.edges[(src, dst)]['bw']
            # 对两个方向的链路容量分别进行添加 (src, dst) -> bw 
            # 即单向的带宽为 bw
            links_capacity[(src, dst)] = bw
            links_capacity[(dst, src)] = bw
        print("链路容量字典为:", links_capacity)
        return links_capacity
    
    def reservations_timeout_thread(self, refresh_rate = 1):
        """ 每当设定的刷新率时间到达时，都会对已有的保留进行超时检查。
        如果有些预留超时则尝试将其进行删除。

        参数:
            refresh_rate (int, optional): 刷新率 (默认为 1 秒)
        """

        while True:
            # 休眠/等待 refresh_rate 秒
            time.sleep(refresh_rate)

            # 对 self.current_reservations 这个数据结构上锁, 
            # 这样做是因为 CLI 也可以访问这些预留
            with self.update_lock:
                to_remove = []
                
                # 迭代所有的预留并更新其超时信息，如果出现超时，则将其删除
                for reservation, data in self.current_reservations.items():
                    data['timeout'] -= refresh_rate
                    # 如果进行计算后的结果小于等于 0, 则将该预留移动到删除列表 to_remove 中
                    if data['timeout'] <= 0:
                        to_remove.append(reservation)

                # 删除所有超时的预留, 通过调用 del_reservation 来实现删除
                for reservation in to_remove:
                    self.del_reservation(*reservation)


    def set_mpls_tbl_labels(self):
        """ 我们设置所有表的默认值以到达网络中的所有主机/网络 """

        # 对拓扑中的所有交换机进行迭代
        for sw_name, controller in self.controllers.items():

            # 获取所有与其直接相连的主机并添加直接 (IPv4) 转发条目
            for host in self.topo.get_hosts_connected_to(sw_name):
                sw_port = self.topo.node_to_node_port_num(sw_name, host)
                host_ip = self.topo.get_host_ip(host)
                host_mac = self.topo.get_host_mac(host)

                # 添加一个直接转发规则
                controller.table_add('FEC_tbl', 'ipv4_forward', ['0.0.0.0/0', str(host_ip)], [str(host_mac), str(sw_port)])
                
            # 获取所有与其直接相连的交换机并添加 MPLS 转发条目
            for switch in self.topo.get_switches_connected_to(sw_name):
                sw_port = self.topo.node_to_node_port_num(sw_name, switch)
                # 反向端口的 MAC 地址 (即 switch 连接到 sw_name 的端口的 MAC 地址 )
                other_switch_mac = self.topo.node_to_node_mac(switch, sw_name)

                # 我们添加一条普通规则和一条倒数第二规则
                controller.table_add('mpls_tbl', 'mpls_forward', [str(sw_port), '0'], [str(other_switch_mac), str(sw_port)])
                controller.table_add('mpls_tbl', 'penultimate', [str(sw_port), '1'], [str(other_switch_mac), str(sw_port)])


    def build_mpls_path(self, switches_path):
        """ 使用一条由交换机组成的路径去构建 mpls 路径。在我们的简化版本中, 标签是端口的索引值。

        参数:
            switches_path (list): 要分配的交换机路径

        返回值:
            list: label path (标签路径)
        """

        # 标签路径 (数据类型: list)
        label_path = []
        # 对路径中的所有交换机对进行迭代
        for current_node, next_node in zip(switches_path, switches_path[1:]):
            # 我们从 topo 对象中获取 current_node -> next_node 的端口号
            label = self.topo.node_to_node_port_num(current_node, next_node)
            # 将获取到的端口号作为标签添加到 label_path 中
            label_path.append(label)
        return label_path
    
    def get_sorted_paths(self, src, dst):
        """ 获取 src、dst 之间的所有路径 (并按长度进行排序)。
        此函数使用 internal networkx API。

        参数:
            src (str): src name
            dst (str): dst name

        返回值:
            list: paths between src and dst
        """

        paths = self.topo.get_all_paths_between_nodes(src, dst)
        # print(src,"和", dst, "之间的所有路径为", paths)
        # 对 src 和 dst 之间的所有路径进行修剪(即删除路径两端的主机，只留下交换机序列)
        paths = [x[1:-1] for x in paths]
        return paths

    def get_shortest_path(self, src, dst):
        """ 计算出两个节点之间的最短路径。
        用于通过始终分配最短路径来测试系统的简单函数。

        参数:
            src (str): src name
            dst (str): dst name

        返回值:
            list: shortest path between src,dst
        """
        
        return self.get_sorted_paths(src, dst)[0]

    def check_if_reservation_fits(self, path, bw):
        """ 检查一个候选的预留是否适合当前网络的状态。使用仅包含交换机的路径, 
        并检查路径上的所有边 (即链路) 是否有足够的空间/带宽。如果没有, 则返回False。

        参数:
            path (list): list of switches
            bw (float): requested bandwidth in mbps

        返回值:
            bool: true if allocation can be performed on path
        """
        
        # 迭代路径上的所有交换机对（边/链路）
        for link in zip(path, path[1:]):
            # 检查路径上的每条链路是否有足够的带宽
            # 必须所有链路均满足带宽要求才可以返回True
            if (self.links_capacity[link] - bw) < 0:
                return False
        return True        
    
    def add_link_capacity(self, path, bw):
        """ 将输入的带宽添加到这条路径上所包含的所有边/链路的容量上。
        当对已有分配进行删除时，会使用此函数。

        参数:
            path (list): list of switches
            bw (float): requested bandwidth in mbps
        """

        # 迭代路径上的所有交换机对（边/链路)
        for link in zip(path, path[1:]):   
            # 向相应的链路上增加设定的带宽  
            self.links_capacity[link] += bw

    def sub_link_capacity(self, path, bw):
        """ 将输入的带宽从这条路径上所包含的所有边/链路的容量上减去。当对进行新的分配时，会使用此函数。

        参数:
            path (list): list of switches
            bw (float): requested bandwidth in mbps
        """
        
        # 迭代路径上的所有的交换机对（边/链路)
        for link in zip(path, path[1:]):
            # 向相应的链路上减去设定的带宽
            self.links_capacity[link] -= bw
    
    def get_available_path(self, src, dst, bw):
        """ 检查从 src 到 dst 的所有路径，并选择可以分配 bw 的最短路径。

        参数:
            src (str): src name
            dst (str): dst name
            bw (float): requested bandwidth in mbps

        返回值:
            list/bool: best path/ False if none
        """
             
        # 获取 src 到 dst 的所有路径，并将所有路径从短到长进行排序
        paths = self.get_sorted_paths(src, dst)

        for path in paths:
            # 检查路径是否有足够的带宽可以进行分配
            if self.check_if_reservation_fits(path, bw):
                return path
        return False

    def get_meter_rates_from_bw(self, bw, burst_size=700000):
        """ 根据 bw 去配置仪表，并返回 CIR 和 PIR 速率以及对应的突发大小。

        参数:
            bw (float): desired bandwdith in mbps
            burst_size (int, optional): 仪表中的桶的最大容量. 默认值为 50000.

        返回值:
            list: [(rate1, burst1), (rate2, burst2)]
        """

        rates = []
        rates.append( (0.125 * bw, burst_size) )
        rates.append( (0.125 * bw, burst_size) )
        return rates
        

    def set_direct_meter_bandwidth(self, sw_name, meter_name, handle, bw):
        """ 设置一个仪表条目(使用一个表的句柄), 以使用 bw (单位: Mbps) 为数据包标记颜色

        参数:
            sw_name (str): switch name
            meter_name (str): meter name
            handle (int): entry handle
            bw (float): desired bandwidth to rate limit
        """
        # 根据 bw 来计算仪表的各项参数
        rates = self.get_meter_rates_from_bw(bw)
        # 根据给定的参数对仪表进行设置
        self.controllers[sw_name].meter_set_rates(meter_name, handle, rates)

    def _add_reservation(self, src, dst, duration, bandwidth, priority, path, update):
        """ 添加或更新单个预留(reservation)

        以单个下划线开头的变量或方法是供内部使用，带有下划线的名称(例如 _spam)应被视为
        API 的非公开部分（无论是函数、方法还是数据成员）

        参数:
            src (str): src name
            dst (str): dst name
            duration (float): reservation timeout
            bandwidth (float): requested bandwidth in mbps
            priority (int): reservation priority
            path (list): switch path were to allocate the reservation
            update (bool): update flag
        """

        # 我们去构建标签路径。为此，我们使用 self.build_mpls_path 并对返回的标签进行反转(逆序)，
        # 因为我们的 rsvp.p4 将以相反的顺序将它们压入堆栈。
        label_path = [str(x) for x in self.build_mpls_path(path)[::-1]]

        # 获取添加一个表规则所需的信息

        # 获取入口交换机作为路径中的第一个节点
        src_gw = path[0]
        # 根据标签路径的长度来计算对应的动作名称
        action = 'mpls_ingress_{}_hop'.format(len(label_path))
        # src lpm address (源地址为最长前缀匹配)
        src_ip = str(self.topo.get_host_ip(src) + '/32')
        # dst exact address (目的地址为精确匹配)
        dst_ip = str(self.topo.get_host_ip(dst))
        # 构建一个包含匹配参数的列表
        match = [src_ip, dst_ip]

        # 如果我们有一条标签路径
        if len(label_path) != 0:

            # 如果条目是新的，我们只需添加它即可
            if not update:
                # 对入口交换机的 FEC_tbl 表的动作进行设置
                entry_handle = self.controllers[src_gw].table_add('FEC_tbl', action, match, label_path)
                # 对入口交换机的直接仪表的带宽进行设置
                self.set_direct_meter_bandwidth(src_gw, 'rsvp_meter', entry_handle, bandwidth)
            # 如果条目需要被更新，我们将使用其句柄对其进行修改  
            else:
                entry = self.current_reservations.get((src, dst), None)
                entry_handle = self.controllers[src_gw].table_modify('FEC_tbl', action, entry['handle'], label_path)
                self.set_direct_meter_bandwidth(src_gw, 'rsvp_meter', entry_handle, bandwidth)
            
            # 如果规则被成功添加，则需要更新控制器链路和预留的结构
            if entry_handle:
                # 减少路径上的所有链路的带宽
                self.sub_link_capacity(path, bandwidth)
                # 对 src -> dst 所对应的预留的信息进行设置或修改
                self.current_reservations[(src, dst)] = {'timeout': (duration), 'bw': (bandwidth), 'priority': (priority), 'handle': entry_handle, 'path': path}
                print('成功添加预留 ({}->{}): path: {}'.format(src, dst, '->'.join(path)))
            else:
                print('\033[91m添加预留失败 ({}->{}): path: {}\033[0m'.format(src, dst, '->'.join(path)))

        else:
            print('警告: 主机连接在同一个交换机上!')


    def add_reservation(self, src, dst, duration, bandwidth, priority):
        """ 添加一个新的预留并考虑其优先级, 这时的添加可能会移动或删除一些其他已有的分配。

        参数:
            src (str): src name
            dst (str): dst name
            duration (float): reservation timeout
            bandwidth (float): requested bandwidth in mbps
            priority (int): reservation priority
        """
        
        # 对 self.current_reservations 数据结构进行上锁。这样做是保证只有一个线程可以同时访问它。
        with self.update_lock:

            # 如果 src -> dst 已存在相应的预留，我们将再次分配它，
            # 只需更新相应的条目 (我们通过设置 UPDATE_ENTRY 标志
            # 并恢复其链路容量), 这样就可以在考虑新容量的情况下完成
            # 一个可能的新 bw/prioirty 的再重新分配。

            UPDATE_ENTRY = False

            # 判断 src -> dst 对应的预留是否已经存在
            # 如果已经存在则表明仅对其进行更新即可
            if self.current_reservations.get((src, dst), None):
                data = self.current_reservations[(src, dst)]
                path = data['path']
                bw = data['bw']
                # 将预留中包含的链路的容量进行增加(即先考虑将其原先所占有的带宽进行虚拟地移除)
                self.add_link_capacity(path, bw)
                # 将 UPDATE_ENTRY 置为 True
                UPDATE_ENTRY = True

            # 然后对其给出的预留条件进行最佳（如果存在）路径检索
            path = self.get_available_path(src, dst, bandwidth)

            # 如果最佳路径存在的话
            if path:   
                # 则添加或更新相应的预留
                self._add_reservation(src, dst, duration, bandwidth, priority, path, UPDATE_ENTRY)

            # 如果不存在最佳路径的话，我们也可以去做一些重新分配的工作
            else:
                # 首先检查是否可以删除那些优先级比较低的流
                previous_links_capacities =  self.links_capacity.copy()
                # 获取当前已存在的所有预留的信息
                for reservation, data in self.current_reservations.items():
                    # 确保我们不会删除所请求的这个预留
                    if reservation == (src, dst):
                        continue
                    # 如果该预留的优先级低于所请求的预留的优先级
                    if data['priority'] < priority:
                        # 则先删除该预留原先所占有的链路带宽
                        self.add_link_capacity(data['path'], data['bw'])

                # 检查所请求的预留是否适合这个已经移除所有比其优先级低的预留的新网络
                path = self.get_available_path(src, dst, bandwidth)

                # 如果可能的话，我们会重新平衡这些较低优先级的预留
                # 对于所请求的预留，如果存在合适的路径则为其进行分配
                if path:                   
                    # 首先将所请求的预留进行添加和分配
                    self._add_reservation(src, dst, duration, bandwidth, priority, path, UPDATE_ENTRY)

                    # 如果可能的话，对其余的预留进行重新分配
                    for reservation, data in sorted(self.current_reservations.items(), key=lambda x: x[1]['priority'], reverse=True):
                        if data['priority'] < priority:
                            src, dst = reservation[0], reservation[1]
                            path = self.get_available_path(src, dst, data['bw'])
                            # 判断该预留是否还可能存在最佳路径
                            if path:   
                                # 如果还存在，则对该预留进行添加或更新
                                self._add_reservation(src, dst, data['timeout'], data['bw'], data['priority'], path, True)
                            else:
                                # 如果不存在，则删除该预留
                                data = self.current_reservations[(src, dst)]
                                path = data['path']
                                bw = data['bw']
                                self.sub_link_capacity(path, bw)
                                print('\033[91m由于更高优先级的分配, 删除 {}->{} 之间的分配/预留!\033[0m'.format(src, dst))
                                self.del_reservation(src, dst)
                # 对于所请求的预留，如果不存在合适的路径的话
                else:
                    # 则恢复原有链路的带宽容量
                    self.links_capacity = previous_links_capacities
                    # 如果这是一个需要更新的条目（UPDATE_ENTRY == True），我们会将其删除
                    if UPDATE_ENTRY:
                        data = self.current_reservations[(src, dst)]
                        path = data['path']
                        bw = data['bw']
                        self.sub_link_capacity(path, bw)
                        print('删除这个新的分配, 其不适合这个网络!')
                        self.del_reservation(src, dst)
                    print('\033[91m预留失败: 没有可用的带宽!\033[0m')

    def del_reservation(self, src, dst):
        """删除 src 和 dst 之间的预留 (如果存在的话)。要删除预留，将使用 self.current_reservations 数据结构
           来检索所有需要的信息。从入口交换机删除预留后，将更新路径上的容量。

        参数:
            src (str): src name
            dst (str): dst name
        """

        # 检查 src -> dst 之间是否已经存在分配
        entry = self.current_reservations.get((src, dst), None)
        # 如果存在的话执行如下操作
        if entry:
            # 获取句柄以删除条目
            entry_handle = entry['handle']
            # 获取源入口交换机
            sw_gw = self.topo.get_host_gateway_name(src)
            # 使用句柄删除表的条目/表项
            self.controllers[sw_gw].table_delete('FEC_tbl', entry_handle, True)
            # 增加相关链路的容量
            self.add_link_capacity(entry['path'], entry['bw'])
            # 从控制器的内存中删除此预留
            del(self.current_reservations[(src, dst)])
            print('\nRSVP 处理删除/超时的预留 ({}->{}): path: {}'.format(src, dst, '->'.join(entry['path'])))
        else:
            print('No entry for {} -> {}'.format(src, dst))

    def del_all_reservations(self):
        """ 删除当前存在的所有的预留 """

        # 对 self.current_reservations 数据结构进行上锁。这样做是保证只有一个线程可以同时访问它。
        with self.update_lock:
            
            # 对所有的预留对做一个拷贝
            reservation_keys = list(self.current_reservations.keys())
            # 依次对其中的每个预留调用 del_reservation 函数进行删除
            for src, dst in reservation_keys:
                self.del_reservation(src, dst)
    

if __name__ == '__main__':
    controller = RSVPController()
    controller.set_mpls_tbl_labels()
    cli = RSVPCLI(controller)