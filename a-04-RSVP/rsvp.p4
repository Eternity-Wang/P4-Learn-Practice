/* -*- P4_16 -*- */

#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4 = 0x0800;
const bit<16> TYPE_MPLS = 0x8847;

#define CONST_MAX_LABELS 	128
#define CONST_MAX_MPLS_HOPS 8

/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;
typedef bit<20> label_t;

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header mpls_t {
    bit<20>   label;
    bit<3>    exp;
    bit<1>    s;
    bit<8>    ttl;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

struct metadata {
    bit<2> meter_color;
}

struct headers {
    ethernet_t                      ethernet;
    mpls_t[CONST_MAX_MPLS_HOPS]     mpls;
    ipv4_t                          ipv4;
}

/*************************************************************************
*********************** P A R S E R  ***********************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_MPLS: parse_mpls;
            TYPE_IPV4: parse_ipv4;
            default: accept;
        }
    }

    state parse_mpls {
        packet.extract(hdr.mpls.next);
        transition select(hdr.mpls.last.s) {
            1: parse_ipv4;
            default: parse_mpls;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition accept;
    }
}

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

    // 直接仪表(仪表类型: 字节)
    direct_meter<bit<2>>(MeterType.bytes) rsvp_meter;

    action drop() {
        mark_to_drop(standard_metadata);
    }

    // 基于 ipv4 进行转发数据包的动作
    action ipv4_forward(macAddr_t dstAddr, egressSpec_t port) {

        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;
        hdr.ethernet.dstAddr = dstAddr;

        standard_metadata.egress_spec = port;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    // MPLS 网络内进行单跳转发的标签堆栈相关操作
    action mpls_ingress_1_hop(label_t label_1) {

        rsvp_meter.read(meta.meter_color);

        hdr.ethernet.etherType = TYPE_MPLS;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_1;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 1;
    }

    // MPLS 网络内进行两跳转发的标签堆栈相关操作
    action mpls_ingress_2_hop(label_t label_1, label_t label_2) {
        rsvp_meter.read(meta.meter_color);

        hdr.ethernet.etherType = TYPE_MPLS;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_1;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 1;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_2;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;
    }

    // MPLS 网络内进行三跳转发的标签堆栈相关操作
    action mpls_ingress_3_hop(label_t label_1, label_t label_2, label_t label_3) {
        rsvp_meter.read(meta.meter_color);

        hdr.ethernet.etherType = TYPE_MPLS;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_1;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 1;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_2;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_3;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;
    }

    // MPLS 网络内进行四跳转发的标签堆栈相关操作
    action mpls_ingress_4_hop(label_t label_1, label_t label_2, label_t label_3, label_t label_4) {
        rsvp_meter.read(meta.meter_color);

        hdr.ethernet.etherType = TYPE_MPLS;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_1;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 1;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_2;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_3;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_4;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;
    }
    
    // MPLS 网络内进行五跳转发的标签堆栈相关操作
    action mpls_ingress_5_hop(label_t label_1, label_t label_2, label_t label_3, label_t label_4, label_t label_5) {
        rsvp_meter.read(meta.meter_color);

        hdr.ethernet.etherType = TYPE_MPLS;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_1;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 1;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_2;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_3;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_4;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_5;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;
    }

    // MPLS 网络内进行六跳转发的标签堆栈相关操作
    action mpls_ingress_6_hop(label_t label_1, label_t label_2, label_t label_3, label_t label_4, label_t label_5, label_t label_6) {
        rsvp_meter.read(meta.meter_color);

        hdr.ethernet.etherType = TYPE_MPLS;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_1;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 1;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_2;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_3;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_4;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_5;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_6;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;
    }
    
    // MPLS 网络内进行七跳转发的标签堆栈相关操作
    action mpls_ingress_7_hop(label_t label_1, label_t label_2, label_t label_3, label_t label_4, label_t label_5, label_t label_6, label_t label_7) {
        rsvp_meter.read(meta.meter_color);

        hdr.ethernet.etherType = TYPE_MPLS;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_1;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 1;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_2;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_3;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_4;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_5;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_6;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_7;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;
    }

    // MPLS 网络内进行八跳转发的标签堆栈相关操作
    action mpls_ingress_8_hop(label_t label_1, label_t label_2, label_t label_3, label_t label_4, label_t label_5, label_t label_6, label_t label_7, label_t label_8) {
        rsvp_meter.read(meta.meter_color);

        hdr.ethernet.etherType = TYPE_MPLS;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_1;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 1;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_2;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_3;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_4;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_5;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_6;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_7;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;

        hdr.mpls.push_front(1);
        hdr.mpls[0].setValid();
        hdr.mpls[0].label = label_8;
        hdr.mpls[0].ttl = hdr.ipv4.ttl - 1;
        hdr.mpls[0].s = 0;
    }
    
    // FEC_tbl 表的相关信息
    // 匹配的键：源 IP 为最长前缀匹配，目的 IP 为精确匹配
    // 执行的动作：ipv4 转发，以及入口交换机的 mpls 标签堆栈压入操作
    // 将直接仪表 rsvp_meter 与 FEC_tbl 表进行关联
    table FEC_tbl {
        key = {
            hdr.ipv4.srcAddr: lpm;
            hdr.ipv4.dstAddr: exact;
        }
        actions = {
            ipv4_forward;
            mpls_ingress_1_hop;
            mpls_ingress_2_hop;
            mpls_ingress_3_hop;
            mpls_ingress_4_hop;
            mpls_ingress_5_hop;
            mpls_ingress_6_hop;
            mpls_ingress_7_hop;
            mpls_ingress_8_hop;
            NoAction;
        }
        default_action = NoAction();
        meters = rsvp_meter;
        size = 256;
    }

    // 基于 mpls 标签进行数据包转发的动作
    action mpls_forward(macAddr_t dstAddr, egressSpec_t port) {

        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;
        hdr.ethernet.dstAddr = dstAddr;

        standard_metadata.egress_spec = port;

        hdr.mpls[1].ttl = hdr.mpls[0].ttl - 1;

        hdr.mpls.pop_front(1);
    }

    // MPLS 网络中的那些倒数第二跳交换机所执行的数据包转发的动作
    action penultimate(macAddr_t dstAddr, egressSpec_t port) {
        
        // 将 etherType 更改为 TYPE_IPV4
        hdr.ethernet.etherType = TYPE_IPV4;

        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;
        hdr.ethernet.dstAddr = dstAddr;
        
        // 计算出 ipv4 的 ttl 值
        hdr.ipv4.ttl = hdr.mpls[0].ttl - 1;

        standard_metadata.egress_spec = port;
        hdr.mpls.pop_front(1);
    }

    // 匹配的键：mpls标签堆栈的栈顶的 “label” 为精确匹配，栈顶的 “bos” 标志为精确匹配
    table mpls_tbl {
        key = {
            hdr.mpls[0].label: exact;
            hdr.mpls[0].s: exact;
        }
        actions = {
            mpls_forward;
            penultimate;
            NoAction;
        }
        default_action = NoAction();
        size = CONST_MAX_LABELS;
    }

    apply {
        /* 入口管道控制逻辑 */
        if(hdr.ipv4.isValid()){
            FEC_tbl.apply();
        }
        if(hdr.mpls[0].isValid()){
            mpls_tbl.apply();
        }

        /* 如果仪表未将数据包标记为绿色则直接丢弃该数据包*/
        if (meta.meter_color != 0)
        {
            drop();
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

control MyComputeChecksum(inout headers  hdr, inout metadata meta) {
    apply {

        // We have modified the ip ttl, so we have to compute the new checksum
        update_checksum(
                hdr.ipv4.isValid(),
                { hdr.ipv4.version,
                hdr.ipv4.ihl,
                hdr.ipv4.diffserv,
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
***********************  D E P A R S E R  *******************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.mpls);
        packet.emit(hdr.ipv4);
    }
}

/*************************************************************************
***********************  S W I T C H  *******************************
*************************************************************************/

V1Switch(
MyParser(),
MyVerifyChecksum(),
MyIngress(),
MyEgress(),
MyComputeChecksum(),
MyDeparser()
) main;
