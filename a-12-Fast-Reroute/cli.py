"""
Inspired in the mininet CLI.
"""
# pylint: disable=keyword-arg-before-vararg,invalid-name

import atexit
import os
import subprocess
import sys
from cmd import Cmd
from select import poll
from textwrap import dedent


class CLI(Cmd):
    " 与节点进行对话的简单命令行界面 "

    prompt = 'link-menu> '

    def __init__(self, controller, stdin=sys.stdin, *args, **kwargs):
        self.controller = controller
        # py 命令的局部变量绑定
        self.locals = {'controller': controller}
        # 尝试去处理输入
        self.inPoller = poll()
        self.inPoller.register(stdin)
        Cmd.__init__(self, *args, stdin=stdin, **kwargs)
        print("\n****************************")
        print("正在检查链路状态并与交换机同步...\n")
        # 检查所有链路的状态并返回出现故障的链路
        failed_links = self.check_all_links()
        # 如果存在故障链路, 则执行如下操作
        if failed_links:
            formatted = ["%s-%s" % link for link in failed_links]
            
            print("当前出现故障的链路为:", ", ".join(formatted))
            # 通知控制器以便网络在启动后正常工作。
            self.do_notify()
        else:
            print("------当前没有发现故障的链路")
        self.do_synchronize()

        self.hello_msg()

        self.initReadline()
        self.run()

    readlineInited = False

    helpStr = dedent("""
    Mangage linkstate with the following commands:
        fail node1 node2    Fail link between node1 and node2.
        reset               Reset all link failures.

    The switch linkstate registers are automatically updated. The controller
    is only notified on demand. You can use the commands:
        synchronize         Manually synchronize linkstate registers.
        notify              Notify controller about failure.
    """).strip()

    header = dedent("""
    ===========================================================================
    Welcome to the Reroute CLI
    ===========================================================================
    """).strip()

    def hello_msg(self):
        """ 初始的介绍界面 """
        print()
        print(self.header)
        print()
        print(self.helpStr)
        print()

    @classmethod
    def initReadline(cls):  # pylint: disable=invalid-name

        " 如果 readline 可用，则设置历史记录 "

        # 只设置一次readline，以防止历史文件倍增
        if cls.readlineInited:
            return
        cls.readlineInited = True
        try:
            from readline import (read_history_file, set_history_length,
                                  write_history_file)
        except ImportError:
            pass
        else:
            history_path = os.path.expanduser('~/.rsvp_controller_history')
            if os.path.isfile(history_path):
                read_history_file(history_path)
                set_history_length(1000)
            atexit.register(lambda: write_history_file(history_path))

    def run(self):

        "运行我们的 cmdloop(), 捕获 KeyboardInterrupt"

        while True:
            try:
                if self.isatty():
                    subprocess.call('stty echo sane intr ^C', shell=True)
                self.cmdloop()
                break
            except KeyboardInterrupt:
                # 输出一条消息 - 除非它也被中断
                # pylint: disable=broad-except
                try:
                    print('\nInterrupt\n')
                except Exception:  # pylint: disable=broad-except
                    pass

    def emptyline(self):
        " 当您在按回车键时，不要重复上一个命令 "
        pass

    def do_help(self, arg):
        " 用于描述可用的 CLI 命令 "
        Cmd.do_help(self, arg)
        if arg == '':
            print(self.helpStr)

    def do_exit(self, _line):
        "Exit"
        assert self  # satisfy pylint and allow override
        return 'exited by user command'

    def do_quit(self, line):
        "Exit"
        return self.do_exit(line)

    def do_EOF(self, line):  # pylint: disable=invalid-name
        "Exit"
        print('\n')
        return self.do_exit(line)

    def isatty(self):
        "用于检测我们的标准输入是 tty 吗？"
        return os.isatty(self.stdin.fileno())

    # 链路管理命令.
    # =========================

    def do_fail(self, line=""):
        """ 使两个节点之间的链路发生故障

        使用方法: fail_link node1 node2
        """
        try:
            node1, node2 = line.split()
            link = (node1, node2)
        except ValueError:
            print("Provide exactly two arguments: node1 node2")
            return

        # 检查输入的两个节点是否为拓扑中的交换机
        for node in (node1, node2):
            if node not in self.controller.controllers:
                print("%s 不是一个有效的节点! " % node, \
                    "您只能使交换机之间相连的链路发生故障! ")
                return

        if node2 not in self.controller.topo.get_intfs()[node1]:
            print("链路 %s-%s 不存在! " % link)
            return

        failed_links = self.check_all_links()
        for failed_link in failed_links:
            if failed_link in [(node1, node2), (node2, node1)]:
                print("链路 %s-%s 已经关闭(down)! " % (node1, node2))
                return

        print("链路 %s-%s 发生故障" % link)

        # self.update_interfaces(link, "down")、
        # 只需要将链路状态设定为down(1)即可
        self.update_linkstate(link, "down")

    def do_reset(self, line=""):  # pylint: disable=unused-argument

        """ 重置所有的接口/链路的状态 """

        failed_links = self.check_all_links()
        for link in failed_links:
            print("对链路 %s-%s 的故障状态进行重置/恢复" % link)
            # self.update_interfaces(link, "up")
            self.update_linkstate(link, "up")

    def do_notify(self, line=""):  # pylint: disable=unused-argument

        """ 向控制器通知故障（或缺少故障）"""

        failed = self.check_all_links()
        print("故障链路为:", failed)
        self.controller.failure_notification(failed)

    def do_synchronize(self, line=""):  # pylint: disable=unused-argument

        """ 确保所有的链路状态寄存器与接口状态相匹配 """

        print("正在将链路状态寄存器与链路状态进行同步...\n")

        switchgraph = self.controller.topo.subgraph(
            list(self.controller.controllers.keys())
        )
        # 依次遍历交换机图中的所有边
        for link in switchgraph.edges:
            # 获取链路两侧的接口和端口
            ifs = self.get_interfaces(link)
            ports = self.get_ports(link)
            for node, intf, port in zip(link, ifs, ports):
                # 判断交换机上的接口 intf 的状态是 up(0) , 还是 down(1)
                state = "0" if not self.state_up(node, port) else "1"
                # 将获取到的状态 state 设置到交换机相应的接口上
                print("交换机%s: 设置端口 %s (%s) 的状态为 %s." %
                      (node, port, intf, state))
                self.update_switch_linkstate(node, port, state)

    # 链路管理助手.
    # ========================

    def check_all_links(self):

        """ 检查所有链路接口的状态 """

        failed_links = []
        switchgraph = self.controller.topo.subgraph(
            list(self.controller.controllers.keys())
        )
        for link in switchgraph.edges:
            # 获取链路两侧的端口号
            port1, port2 = self.get_ports(link)
            node1, node2 = link
            # 判断两个接口 if1 和 if2 的状态是否都为 up 
            if (self.state_up(node1, port1) and self.state_up(node2, port2)):
                # 如果不是, 则认为该链路出现故障
                failed_links.append(link)
        return failed_links

    
    def state_up(self, switch, port):

        """ 判断该端口的 state 为 up 还是 down """

        control = self.controller.controllers[switch]
        return bool(control.register_read('linkState', port))

    # @staticmethod
    # def if_up(interface):

    #     """ 如果接口已经 up, 则返回 True, 否则返回 False """

    #     cmd = ["ip", "link", "show", "dev", interface]
    #     return b"state UP" in subprocess.check_output(cmd)

    # def update_interfaces(self, link, state):
    
    #     """ 将链路上的两个接口设置为相应的状态 (启动 up 或关闭 down) 
            
    #         不建议使用此函数, 详见update_if函数介绍"""

    #     # 获取链路两侧的接口
    #     if1, if2 = self.get_interfaces(link)
    #     # 更新这两个接口的状态信息
    #     self.update_if(if1, state)
    #     self.update_if(if2, state)

    # @staticmethod
    # def update_if(interface, state):

    #     """ 设置接口的状态 (启动up或关闭down)
            
    #         不建议使用此命令, 会出现bug
    #         会导致整个交换机失效 """

    #     print("设置接口 '%s' 的状态为 '%s'." % (interface, state))

    #     # 运行成功的关键, 参考 Blink 那篇如何 down 掉某条链路的方法
    #     # https://github.com/nsg-ethz/Blink
    #     cmd = ["sudo", "ifconfig", interface, state]
    #     subprocess.check_call(cmd)

    def get_interfaces(self, link):

        """ 返回一个元组, 元素为链路两端的接口(interface) """

        node1, node2 = link
        if_12 = self.controller.topo.get_intfs()[node1][node2]['intfName']
        if_21 = self.controller.topo.get_intfs()[node2][node1]['intfName']
        # print("端口号对应关系为: %s <-> %s"% (if_12, if_21))
        return if_12, if_21

    def get_ports(self, link):

        """ 返回一个元组, 元素为链路两端的接口(interface)对应的端口号 """

        node1, node2 = link
        if1, if2 = self.get_interfaces(link)
        port1 = self.controller.topo.get_node_intfs(fields=['port'])[node1][if1]
        port2 = self.controller.topo.get_node_intfs(fields=['port'])[node2][if2]
        # print("端口号对应关系为: %s <-> %s" % (port1, port2))
        return port1, port2

    def update_linkstate(self, link, state):

        """ 更新链路的两个接口所对应的交换机的链路状态寄存器

        寄存器数组按端口号进行索引，例如，端口 0 的状态存储在索引 0 处
        """
        
        # 获取链路 link 两端的节点 node1 和 node2
        node1, node2 = link
        # 获取链路 link 两端的端口号 port1 和 port2
        port1, port2 = self.get_ports(link)
        
        # 将状态进行转换, 即 down 对应 1, up 对应 0
        _state = "1" if state == "down" else "0"
        print("将 %s:%s 和 %s:%s 的链路状态设置为 %s (%s)." %
              (node1, port1, node2, port2, _state, state))
        self.update_switch_linkstate(node1, port1, _state)
        self.update_switch_linkstate(node2, port2, _state)

    def update_switch_linkstate(self, switch, port, state):

        """ 更新交换机上的链路状态寄存器 """

        control = self.controller.controllers[switch]
        control.register_write('linkState', port, state)
