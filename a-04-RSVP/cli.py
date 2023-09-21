"""
Inspired in the mininet CLI.
"""

import subprocess
from cmd import Cmd
from os import isatty
from select import poll, POLLIN
import select
import sys
import os
import atexit

class RSVPCLI( Cmd ):
    " 与节点交互的简单的命令行 (CLI) 接口 "

    prompt = 'rsvp-menu> '

    def __init__( self, controller, stdin=sys.stdin, script=None,
                  *args, **kwargs ):

        self.controller = controller
        # py 命令的本地变量绑定
        self.locals = { 'controller': controller }
        # 尝试去处理输入
        self.inPoller = poll()
        self.inPoller.register( stdin )
        self.inputFile = script
        Cmd.__init__( self, *args, stdin=stdin, **kwargs )

        self.hello_msg()
        if self.inputFile:
            self.do_source( self.inputFile )
            return

        self.initReadline()
        self.run()

    readlineInited = False

    def hello_msg(self):
        """ 关于 RSVP CLI 的使用说明界面的打印 """

        print('======================================================================')
        print('Welcome to the RSVP CLI')
        print('======================================================================')
        print('You can now make reservations for your hosts in the network.')
        print('To add a reservation run:')
        print('add_reservation <src> <dst> <duration> <bw> <priority>')
        print('')
        print('To delete a reservation run: ')
        print('del_reservation <src> <dst>')
        print('')


    @classmethod
    def initReadline( cls ):
        "如果 readline 可用，则设置历史记录"
        # 只设置一次 readline，从而防止历史文件的倍增
        if cls.readlineInited:
            return
        cls.readlineInited = True
        try:
            from readline import ( read_history_file, write_history_file,
                                   set_history_length )
        except ImportError:
            pass
        else:
            history_path = os.path.expanduser( '~/.rsvp_controller_history' )
            if os.path.isfile( history_path ):
                read_history_file( history_path )
                set_history_length( 1000 )
            atexit.register( lambda: write_history_file( history_path ) )

    def run( self ):
        "运行我们的 cmdloop(), 捕获 KeyboardInterrupt"
        while True:
            try:
                if self.isatty():
                    subprocess.call( 'stty echo sane intr ^C',shell=True)
                self.cmdloop()
                break
            except KeyboardInterrupt:
                # 输出一条消息 - 除非它也被中断
                # pylint: disable=broad-except
                try:
                    print( '\nInterrupt\n' )
                except Exception:
                    pass
                # pylint: enable=broad-except

    def emptyline( self ):
        "当您在按回车键时，不要重复上一个命令。"
        pass

    def getLocals( self ):
        "py 命令的本地变量绑定"
        self.locals.update( self.mn )
        return self.locals
    
    # 帮助字符串，用于对一些 CLI 命令的使用方法进行介绍和描述
    helpStr = (
        'To add a reservation run:\n'
        'add_reservation <src> <dst> <duration> <bw> <priority>\n'
        '\n'
        'To delete a reservation run: \n'
        'del_reservation <src> <dst>\n'
        ''
    )

    def do_help( self, line ):
        "描述可用的 CLI 命令."
        Cmd.do_help( self, line )
        if line == '':
            print( self.helpStr )
  
    def do_exit( self, _line ):
        "Exit"
        assert self  # satisfy pylint and allow override
        return 'exited by user command'

    def do_quit( self, line ):
        "Exit"
        return self.do_exit( line )

    def do_EOF( self, line ):
        "Exit"
        print( '\n' )
        return self.do_exit( line )

    def isatty( self ):
        "用于检测我们的标准输入是 tty 吗？"
        return isatty( self.stdin.fileno() )

    """
    一些 RSVP 中需要用到的命令
    """

    def do_add_reservation(self, line=""):
        """使用 MPLS 添加一个预留(reservation)

           用法: add_reservation <src> <dst> <duration> <bw> <priority>
        """

        # 获取输入的参数 (这块是将输入的参数按空格符号进行分隔并依次存入到 args 这个列表中)
        args = line.split()
        # 默认值
        duration = 9999
        bw = 1
        priority = 1

        # 根据args列表的长度来计算出参数的数量
        # 并根据对应的数量将 args 中的值赋给相应的变量
        if len(args) < 2:
            print("Not enough args!")
            return
        
        elif len(args) == 2:
            src, dst =  args
        
        elif len(args) == 3:
            src, dst, duration =  args
        
        elif len(args) == 4:
            src, dst, duration, bw =  args
        
        elif len(args) == 5:
            src, dst, duration, bw,  priority =  args
        
        else:
            print("Too many args!")
            return

        # 将参数的数据类型 (原先都是字符串类型) 进行相应的转换
        duration = float(duration)
        bw = float(bw)
        priority = int(priority)
        
        # 调用控制器的 add_reservation 函数添加一个条目
        res = self.controller.add_reservation(src, dst, duration, bw, priority)


    def do_del_reservation(self, line=""):
        """ 删除一个预留(reservation)
         
            用法: del_reservation <src> <dst> """

        # 获取输入的参数 
        args = line.split()

        if len(args) < 2:
            print("Not enough args!")
            return
        
        elif len(args) == 2:
            src, dst =  args[:2]
        
        else:
            print("Too many args!")
            return

        # 根据输入的源 IP 和目的 IP 地址，调用控制器的 del_reservation 函数来删除对应的条目
        res = self.controller.del_reservation(src, dst)

    def do_del_all_reservations(self, line =""):
        """ 删除所有的预留(reservation) """

        # 调用控制器的 del_all_reservations 函数来删除所有已存在的条目
        res = self.controller.del_all_reservations()

    def do_print_reservations(self, line = ""):
        """ 依次打印当前所有已有预留(reservation)的相关信息 """

        print("当前已有的预留为:")
        print("---------------------")
        for i, ((src, dst), data) in enumerate(self.controller.current_reservations.items()):
            # 打印的数据依次为: 序列号 i, 源地址 src, 目的地址 dst, 路径信息 data['path'], 
            # 带宽 data['bw'], 优先级 data['priority'], 超时信息 data["timeout"]
            print("{:>3} {}->{} : {}, bw:{}, priority:{}, timeout:{}".format(i, src, dst, 
                "->".join(data['path']), data['bw'], data['priority'], data["timeout"] ))
    
    def do_print_link_capacity(self, line=""):
        """ 打印当前所有已有链路的容量 """

        print("当前已有的链路容量为:")
        print("---------------------")
        for edge, bw in self.controller.links_capacity.items():
            # 打印的数据依次为: 边/链路 edge, 带宽 bw
            print("{} -> {}".format(edge, bw))
        