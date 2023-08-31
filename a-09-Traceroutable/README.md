# Traceroutable Network

## Introduction

在本练习中，我们将使用一个附加功能来扩展我们的 P4 路由器：响应 `traceroute` 数据包，即那些 IPv4 TTL（生存时间）值等于 1 的数据包。如果路由器收到这样的数据包，它会生成一个ICMP `Time Exceeded` 消息并将其发送回这个过期数据包的原始发送者。

因此，我们的目标是使 `traceroute` 或类似工具在我们的网络中运行。

简而言之，traceroute 的工作原理如下：它发送多个以 `TTL=1` 开头的数据包，并将每个后续数据包的 TTL 依次加 1。正如您所知，每经过一个互联网内的路由器都会将数据包的 IP TTL 减 1，并在等于 0 时发回 ICMP 消息。通过发送 TTL 不断增加的数据包，traceroute 能够 `trace` 数据包从源到给定目的地的路径。

有关 traceroute 如何工作的详细描述，请查看[维基百科文章](https://en.wikipedia.org/wiki/Traceroute)。有关 ICMP（即用于回复过期跟踪路由数据包的协议）的更多信息，请查看此[维基百科文章](https://en.wikipedia.org/wiki/Internet_Control_Message_Protocol#Time_exceeded) 或其 [RFC] （https://tools.ietf.org/html/rfc792）。

## Before starting

在您开始这个练习之前，请更新 `p4-utils`, 上周修复了一些新功能和错误：

```bash
cd ~/p4-tools/p4-utils
git pull
```

此外，您需要 `traceroute` 工具来进行此练习（它可能已经安装）。通过在终端中运行以下命令来安装它：

```bash
sudo apt-get install traceroute
```

### What is already provided

对于本练习，我们为您提供以下文件：

- `p4app.json`: describes the topology we want to create with the help of mininet and p4-utils package.
- `network.py`: a Python scripts that initializes the topology using *Mininet* and *P4-Utils*. One can use indifferently `network.py` or `p4app.json` to start the network.
- `p4src/ecmp.p4`: we will use the solution of the [03-ECMP](../03-ECMP) exercise as starting point.
- `send.py`: 一个小的 python 脚本，用于生成具有不同 tcp 端口的多个数据包。
- `routing-controller.py`: 路由控制器框架。控制器使用全局拓扑信息和简单的交换机 `thrift_API` 来填充路由表。
- `topology_generator.py`: 自动生成 `p4app` 配置文件的 python 脚本。它允许您生成 3 种类型的拓扑：线性、圆形和随机（具有节点数和度数）。使用 `-h` 选项运行它以查看其包含的命令行参数。
- `network_generator.py`: 自动生成 `network.py` 脚本的 Python 脚本。它允许您生成 3 种类型的拓扑：线性、圆形和随机（具有节点数和度数）。使用 `-h` 选项运行它以查看其包含的命令行参数。
- `traceroute.py`: python 脚本，使用 `tcp` 探针实现一个简单版本的 traceroute 。它可用于编写跟踪路由测试脚本。

#### Notes about p4app.json

对于本练习，我们将使用 `l3` 分配策略。`mixed` 分配策略为：连接到同一个交换机的主机形成一个子网，每个交换机形成一个不同的域。与 `mixed` 策略不同的是，在 `l3` 分配中，我们认为交换机仅在第 3 层工作，这意味着每个接口必须属于不同的子网。如果您使用 `hY` 和 `sX` 进行命名（例如 h1、h2、s1、s2...），IP 分配将如下所示：

   1. 主机 IP: `10.x.y.2`, 这里 `x` 是网关交换机的 ID, 而 `y` 则是主机的 ID.
   2. 直接连接主机的交换机端口：`10.x.y.1`，这里 `x` 是网关交换机的 ID, 而 `y` 则是主机的 ID。
   3. 交换机到交换机的端口：`20.sw1.sw2.<1,2>`。其中 `sw1` 是第一个交换机的 id（遵循 `p4app` 中链路定义的顺序）， `sw2` 是第二个交换机的 id。最后一个字节对于 sw1 的接口为 1，对于 sw2 的接口为 2。

请注意，这是我们第二次为交换机分配 IP 地址。然而，值得注意的是，实际上 `p4-utils` 不会将这些 IP 分配给交换机，但它会保存它们，以便它们可以 `virtually` 用于某些交换机功能（我们稍后会看到这意味着什么）。

您可以在 `p4-utils` [文档](https://github.com/nsg-ethz/p4-utils#topology-description)中找到有关 `p4app.json` 的所有文档。

## Understanding traceroute

在开始这个实现之前，我们将看一下由 `traceroute` 发送和接收的数据包。为此，请打开终端并输入 `sudo wireshark &` 以打开 Wireshark。然后，选择接口 `eth0` 并开始捕获流量。您将看到大量正在发送和接收的数据包，要删除它们，您可以在过滤器栏中输入
以下过滤规则： `ip.ttl < 10 || icmp`。
现在在终端中运行以下命令：

```bash
sudo traceroute -n -q 1 -f 1 -m 1 -T ethz.ch
```

这将向 `ethz.ch` 发送一个带有 `TTL=1` 的 traceroute（`TCP`）数据包。在 Wireshark 中，您应该看到一个 `TCP` 数据包以及相应的 `ICMP` reply。仔细查看这些数据包，了解路由器如何构建这些 `ICMP` reply。您可以使用 `ethz.ch` 的 `ICMP` reply 作为参考。例如，您可以查看 `IP` 报头如何变化、以及 `ICMP` 报头和正文包含什么内容等。

## Implementing the traceroutable switch

采用上一个练习中的解决方案（P4 代码和 `routing-controller.py`）。为了实现我们的 traceroutable 交换机，我们必须添加两个内容：首先，我们必须向 P4 程序添加一个新表，将 egress_ports 映射到该端口在交换机上对应的 `IP` 地址。您还必须使用一个小函数来扩展控制器，该函数用于为每个交换机填充此表。其次，我们必须扩展 P4 程序，以便交换机使用 ICMP reply 来回复那些 `TTL=1` 的数据包，而且是回复到原始发送者。

#### Adding the output port to IP table

在我们对 P4 中的过期数据包生成 ICMP reply 之前，我们必须向之前练习中已有的代码中添加一个新表。该表将在 ICMP reply 过程中用于设置交换机生成的数据包的源 `ipv4` 地址。然后，traceroute 工具将使用此 IP 地址来识别数据包来自哪个路由器（和接口）。

你需要做如下几个事情:

1. 定义一个名为 `icmp_ingress_port` 的表，该表与数据包的 `ingress_port` 相匹配（该入口端口将用作 ICMP reply 的出口端口）。该表将调用一个动作 (`set_src_icmp_ip`)，该动作将 IP 地址作为参数并将其设置为 `hdr.ipv4_icmp` 的源 IP 地址。您将在下一节中了解这个 `ipv4_icmp` 报头是什么。

2. 在 `routing-controller.py` 中实现 `set_icmp_ingress_port_table` 函数。特别是，我们希望为交换机的每个端口分配一个单独的 IP 地址。为此，您必须使用从入口端口到与相应端口关联的 IP 地址的映射来填充`icmp_ingress_port` 表。要获取有关 IP 端口的信息，您必须使用 `self.topo` 对象。有关更多信息，请参阅[文档](https://github.com/nsg-ethz/p4-utils#topology-object)。提示：有一个函数可以获取某个节点拥有的所有端口，通过该函数您应该能够获取它们的 IP 和端口号。

#### Replying with ICMP packets

要实现 ICMP 数据包回复/应答系统，您应该：

1. 将 ICMP 报头添加到 `headers.p4` 文件中。

2. 使用 `icmp` 报头和第二个 `ipv4` 报头（您可以将其称为 `ipv4_icmp`）扩展 `headers` 这个结构体。正如您在traceroute 测试期间应该看到的那样，ICMP 数据包应包含其自己的 `ipv4` 报头和过期/超时数据包的 `ipv4` 报头。正如您从报头和解析器（来自 ECMP 解决方案）中看到的，我们仅将 TCP 视为传输层协议（而不是 UDP）。因此，您可以在实现中重点关注 TCP（和 IP）数据包。

3. 使用两个新报头来扩展去解析器的控制块。请确保以正确的顺序发出这些东西/报头。为此，请再次检查 ICMP 数据包的外观。

4. 我们现在开始扩展入口管道的实现。这里，可以先检查接收到的数据包的 TTL 值是否为 `>1`。如果是这样，您将照常转发数据包（使用 ECMP）。

5. 如果 TTL 等于 `1`（并且数据包是 `ipv4` 和 `tcp` 有效），则数据包将在此路由器处过期，您需要将应答发送回发送者。（确保该数据包不经过正常的转发表）。要将收到的 TCP 数据包转换为 ICMP reply，需要执行以下操作：
    - 将附加/额外的报头（`ipv4_icmp`、`icmp`）设置为有效（通过调用 `hdr.X.setValid()`）
    - 设置出口端口，以便数据包通过其到达的端口进行发送
    - 交换源 MAC 地址和目的 MAC 地址
    - 将源 IP 地址设置为数据包到达的端口所属的 IP 地址（使用上面的表 `icmp_ingress_port`）
    - 为 `ipv4_icmp` 和 `icmp` 报头设置正确的值（您可以使用之前在 Wireshark 中捕获的数据包作为模板）
    - 确保您将 `ipv4_icmp.totalLen` 设置为正确的值，否则 wireshark（或其他工具）将无法正确计算校验和。
    - 将数据包截断为 70 字节（使用 `truncate((bit<32>)70);`），以从原始数据包中删除剩余部分。

6. 由于 IP 报头和 ICMP 报头都包含校验和，因此您需要在 `MyComputeChecksum` 控件中计算它们。您可以使用之前练习中的 IP 校验和作为 `ipv4_icmp` 校验和的模板。要计算 `icmp` 报头的校验和，您必须将 ICMP 报头中的所有字段与有效负载（原始 IP 报头 + tcp 报头中的前 8 个字节）一起进行哈希处理。对于此校验和，请使用之前使用的相同算法（`HashAlgorithm.csum16`）。

## Testing your solution

完成实现后，您可以使用 `traceroute.py` 脚本或真正的 `traceroute` 工具来测试这个程序。如果您使用 `traceroute` 工具，请记住，我们仅实现了对 TCP 数据包的回复，而该工具默认发送 UDP 数据包。因此，请添加 `-T` 参数以使用 TCP 数据包。

1. 启动拓扑（这也将编译并加载程序）。
   
   ```bash
   sudo p4run
   ```

   or
   ```bash
   sudo python network.py
   ```

2. 运行控制器.

   ```bash
   python routing-controller.py
   ```

3. 检查您是否能够 ping 通:

   ```
   mininet> pingall
   ```

4. 在两个主机之间进行 traceroute :

   您可以在主机中使用我们自己的实现（`traceroute.py`）或 Mininet 中默认的 `traceroute` 工具：

   ```python -i traceroute.py
   for sport in range(6000,6020):
       print(traceroute(dst="10.6.2.2",sport=sport, dport=80))
   ```

   ```bash
   mininet> h1 traceroute -n -w 0.5 -q 1 -T --sport=<src_port> --port=<dst_port> 10.6.2.2
   ```
   (为了使其更快, 我们关闭了 DNS 查询 (`-n`), 减少了等待时间 `-w`, 每个 TTL 仅发送单个数据包 (`-q`) 以及固定的源和目的端口号（`--sport`、`--dport`），从而在 ECMP 情况下获取流的实际路径)


  请注意，第二个路由器（s2、s3、s4 或 s5）将始终指示/表明具有给定 5 元组的流在我们的简单拓扑中将采用哪条路径。

### Testing with another topology

与上一个练习一样，您可以使用我们为您提供的 `topology_generator.py` 脚本来测试您的解决方案是否可以在其他拓扑下使用，该脚本会生成随机拓扑：

```bash
python topology_generator --output_name <name.json> --topo random --n <number of switches to use> -d <average switch diamiter>
```

这将创建一个具有 `n` 个交换机的随机拓扑，这些交换机平均具有 `d` 个接口/端口（取决于 `n`，`d` 也许不可能）。此外，每个交换机都会有一个直接连接到它的主机（因此具有 `n` 个主机）。

运行随机拓扑:

```bash
sudo p4run --config <name.json>
```

如果您想使用 Python 脚本而不是 JSON 文件，您可能需要运行：

```bash
python network_generator.py --output_name <name.py> --topo random --n <number of switches to use> -d <average switch diamiter>
```

and
```bash
sudo python <name.py>
```

执行我们在上一节中执行的其余步骤。通过在两个主机之间运行多个 traceroutes，您将能够发现正在使用哪个路径（或多个路径）!

#### Some notes on debugging and troubleshooting


如果您没有收到对 traceroute 查询的回复 (reply)，您可以使用 Wireshark 来查看数据包（即捕获主机的接口）。Wireshark 会告诉您数据包是否无法解析（例如，因为结构不正确）或者校验和是否不正确。

我们在文档部分添加了一个[小指南](https://github.com/nsg-ethz/p4-learning/wiki/Debugging-and-Troubleshooting)。当事情没有按预期进行时，可以将其用作参考。
