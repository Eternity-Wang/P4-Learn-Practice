/* -*- P4_16 -*- */
#include <core.p4>
#include <v1model.p4>

//My includes
#include "include/headers.p4"
#include "include/parsers.p4"

// 下一跳的数量
#define N_PREFS 128
// 存放端口号的变量/常量大小
#define PORT_WIDTH 32
// 端口的数量
#define N_PORTS 128    



/*************************************************************************
************   C H E C K S U M    V E R I F I C A T I O N   *************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {  }
}

/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    // 用于查阅/查询默认下一跳的端口号的寄存器
    // (分为主要下一跳和备份下一跳这两个寄存器)
    register<bit<PORT_WIDTH>>(N_PREFS) primaryNH;
    register<bit<PORT_WIDTH>>(N_PREFS) alternativeNH; 

    // 包含链路状态的寄存器  0: 没有问题. 1: 链路故障.
    // 该寄存器将由 CLI.py 进行更新, 你只需要读取它即可
    register<bit<1>>(N_PORTS) linkState;

    // 重写 MAC 地址
    action rewriteMac(macAddr_t dstAddr){
	    hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;
        hdr.ethernet.dstAddr = dstAddr;
	}

    action drop() {
        mark_to_drop(standard_metadata);
    }

    // 根据索引读取默认下一跳的端口号和链路状态
    action read_port(bit<32> index){
        // 将索引值赋给 meta.index
        meta.index = index;

        // 读取主要下一跳并将读取的结果(即端口号)写入到 meta.nextHop 中
        primaryNH.read(meta.nextHop, meta.index);
        
        // 读取默认下一跳(即meta.nextHop)的链路状态
        linkState.read(meta.linkState, meta.nextHop);
    }

    // 读取备份下一跳的端口号
    action read_alternativePort(){
        
        // 读取备份下一跳并将读取的结果写入到 meta.nextHop 中
        alternativeNH.read(meta.nextHop, meta.index);
    }


    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            read_port;
            drop;
        }
        size = 512;
        default_action = drop;
    }


    table rewrite_mac {
        key = {
             meta.nextHop: exact;
        }
        actions = {
            rewriteMac;
            drop;
        }
        size = 512;
        default_action = drop;
    }
    
    apply {
        if (hdr.ipv4.isValid()){
            ipv4_lpm.apply();

            // 判断下一跳的链路是否出现故障
            if (meta.linkState != 0){
                // 出现故障则读取备份下一跳的端口号
                read_alternativePort();
            }

            // 将 meta.nextHop (即下一跳的端口号) 赋给 egress_spec(用于转发数据包)
            standard_metadata.egress_spec = (bit<9>) meta.nextHop;
            hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
            // 并且更新数据包的 MAC 地址
		    rewrite_mac.apply();    
        }
    }
}
/*************************************************************************
****************  E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {

    apply {

    }

}

/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
     apply {
      update_checksum(
      hdr.ipv4.isValid(),
            { hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.dscp,
              hdr.ipv4.ecn,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}




/*************************************************************************
***********************  S W I T C H  *******************************
*************************************************************************/

//switch architecture
V1Switch(
MyParser(),
MyVerifyChecksum(),
MyIngress(),
MyEgress(),
MyComputeChecksum(),
MyDeparser()
) main;
