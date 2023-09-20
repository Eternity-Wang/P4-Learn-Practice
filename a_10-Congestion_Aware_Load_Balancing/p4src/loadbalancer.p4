/* -*- P4_16 -*- */
#include <core.p4>
#include <v1model.p4>

//My includes
#include "include/headers.p4"
#include "include/parsers.p4"

// 寄存器的大小为 1024
#define REGISTER_SIZE 1024
// 寄存器中每个元素的大小为 32
#define REGISTER_WIDTH 32

// 对数据包的类型进行定义
#define PKT_INSTANCE_TYPE_NORMAL 0
#define PKT_INSTANCE_TYPE_INGRESS_CLONE 1
#define PKT_INSTANCE_TYPE_EGRESS_CLONE 2
#define PKT_INSTANCE_TYPE_COALESCED 3
#define PKT_INSTANCE_TYPE_INGRESS_RECIRC 4
#define PKT_INSTANCE_TYPE_REPLICATION 5
#define PKT_INSTANCE_TYPE_RESUBMIT 6


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
    
    // 
    register <bit<REGISTER_WIDTH>>(REGISTER_SIZE) loadbalance_seed;

    action drop() {
        mark_to_drop(standard_metadata);
    }

    // 用于设置出口节点的类型(主机或交换机)
    action set_egress_type (bit<4> egress_type){
        meta.egress_type = egress_type;
    }

    // 对 egress_spec 进行精确匹配, 并输出该端口对应的节点类型
    table egress_type {
        key = {
            standard_metadata.egress_spec: exact;
        }

        actions = {
            set_egress_type;
            NoAction;
        }
        size=64;
        default_action = NoAction;
    }

    action update_flow_seed(){
        // 寄存器的索引号
        bit<12> register_index;
        bit<32> seed;

        // 随机生成 seed 的值
        random(seed, (bit<32>)0, (bit<32>)1234567);

        // 对五元组进行哈希计算出 register_index 的值
        hash(register_index,
	    HashAlgorithm.crc16,
	    (bit<1>)0,
	    { hdr.ipv4.dstAddr,
	      hdr.ipv4.srcAddr,
              hdr.tcp.srcPort,
              hdr.tcp.dstPort,
              hdr.ipv4.protocol},
	      (bit<12>)REGISTER_SIZE);

        // 将 seed 写入到寄存器中 register_index 指向的元素中
	    loadbalance_seed.write((bit<32>)register_index, seed);
    }

    // 设置 ECMP 组的 ID 号及用于转发的哈希值信息(即ecmp_hash)
    action ecmp_group(bit<14> ecmp_group_id, bit<16> num_nhops){

        bit<12> register_index;
        bit<32> seed;

        // 对五元组进行哈希计算出 register_index 的值
        hash(register_index,
	    HashAlgorithm.crc16,
	    (bit<1>)0,
	    { hdr.ipv4.srcAddr,
	      hdr.ipv4.dstAddr,
              hdr.tcp.srcPort,
              hdr.tcp.dstPort,
              hdr.ipv4.protocol},
	      (bit<12>)REGISTER_SIZE);
        
        // 读取该索引对应的 seed 值
	    loadbalance_seed.read(seed, (bit<32>)register_index);

        // 通过对五元组 + seed 一起进行哈希
        // 计算出最终要转发的下一跳信息 emcp_hash
        hash(meta.ecmp_hash,
	    HashAlgorithm.crc16,
	    (bit<1>)0,
	    { hdr.ipv4.srcAddr,
	      hdr.ipv4.dstAddr,
              hdr.tcp.srcPort,
              hdr.tcp.dstPort,
              hdr.ipv4.protocol,
              seed},
	      num_nhops);
        
        // 将 ecmp_group_id 赋给用户自定义元数据 meta 的对应元素
	    meta.ecmp_group_id = ecmp_group_id;
    }

    // 设置下一跳转发信息的动作
    action set_nhop(macAddr_t dstAddr, egressSpec_t port){

        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;
        hdr.ethernet.dstAddr = dstAddr;
        standard_metadata.egress_spec = port;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;

    }

    // 通过对 ecmp_group_id 和对应的 ecmp_hash 进行精确匹配
    // 来执行相应的 set_nhop 动作
    table ecmp_group_to_nhop {
        key = {
            meta.ecmp_group_id: exact;
            meta.ecmp_hash: exact;
        }
        actions = {
            drop;
            set_nhop;
        }
        size = 1024;
    }

    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            set_nhop;
            ecmp_group;
            drop;
        }
        size = 1024;
        default_action = drop;
    }

    apply {

        if (standard_metadata.instance_type == PKT_INSTANCE_TYPE_INGRESS_RECIRC){
            // 交换源 IP 地址和目的 IP 地址
            bit<32> src_ip = hdr.ipv4.srcAddr;
            hdr.ipv4.srcAddr = hdr.ipv4.dstAddr;
            hdr.ipv4.dstAddr = src_ip;
            // 将以太网类型设置为 TYPE_FEEDBACK (反馈类型)
            hdr.ethernet.etherType = TYPE_FEEDBACK;
        }

        // 仅当数据包为 IP 包且 TTL 大于 1 时才执行下述转发
        if (hdr.ipv4.isValid() && hdr.ipv4.ttl > 1){
            switch (ipv4_lpm.apply().action_run){
                // 如果 ipv4_lpm 表中的 ecmp_group 动作被执行
                // 则将调用 ecmp_group_to_nhop 表
                ecmp_group: {
                    ecmp_group_to_nhop.apply();
                }
            }
        }

        // 对 egress_spec 相连的节点的类型进行判断
        egress_type.apply();

        // 如果该数据包的实例类型为 NORMAL 且为反馈类型的数据包且 egress_spec 对应的节点类型为主机
        // 则表明拥塞产生的反馈数据包已经到达其对应的主机进入网络的第一个交换机处, 
        // 因此需要更新该流的 seed 值(更新 seed 值后哈希出的 meta_hash 也会变化, 从而实现路由到其他路径)
        if (standard_metadata.instance_type == PKT_INSTANCE_TYPE_NORMAL && hdr.ethernet.etherType == TYPE_FEEDBACK && meta.egress_type == TYPE_EGRESS_HOST){
            // 更新该流的 seed 值
            update_flow_seed();
            // 丢弃该反馈数据包
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
    
    // 用于存放不同流的反馈包发出的时间戳的寄存器
    register <bit<48>>(REGISTER_SIZE) feedback_ts;

    action read_feedback_ts(){

        // 根据流的五元组哈希计算出对应的寄存器索引 feedback_register_index
        hash(meta.feedback_register_index,
	    HashAlgorithm.crc16,
	    (bit<1>)0,
	    { hdr.ipv4.srcAddr,
	      hdr.ipv4.dstAddr,
              hdr.tcp.srcPort,
              hdr.tcp.dstPort,
              hdr.ipv4.protocol},
	      (bit<12>)REGISTER_SIZE);

    // 根据 feedback_register_index 从寄存器的相应位置中读取值并写入 meta.feedback_ts
    // 即读取该流最新的反馈数据包发出的时间戳
	feedback_ts.read(meta.feedback_ts, (bit<32>)meta.feedback_register_index);

    }

    apply {
        // 克隆数据包, 用于生成探针
        // 如果当前数据包的类型为 EGRESS_CLONE, 则对其进行recirculate
        if (standard_metadata.instance_type == PKT_INSTANCE_TYPE_EGRESS_CLONE){
            recirculate_preserving_field_list(2);
        }

        // 如果数据包的实例类型为 NORMAL 且数据包不为反馈类型的包
        else if (standard_metadata.instance_type == PKT_INSTANCE_TYPE_NORMAL && hdr.ethernet.etherType != TYPE_FEEDBACK) {

            if (hdr.tcp.isValid()){

                // 判断是否遥测报头是否生效
                if (hdr.telemetry.isValid()){
                    // 判断当前交换机的 enq_qdepth 是否大于遥测报头中的 enq_qdepth
                    // 且 egress_spec 对应的节点类型为交换机
                    if (hdr.telemetry.enq_qdepth < (bit<16>)standard_metadata.enq_qdepth && meta.egress_type == TYPE_EGRESS_SWITCH){
                        // 更新遥测报头中的 enq_qdepth 值
                        hdr.telemetry.enq_qdepth = (bit<16>)standard_metadata.enq_qdepth;
                    }
                    // 如果 egress_spec 对应的节点类型为主机
                    else if (meta.egress_type == TYPE_EGRESS_HOST){
                        // 将 etherType 更改为 TYPE_IPV4
                        hdr.ethernet.etherType = TYPE_IPV4;
                        // 使遥测报头失效
                        hdr.telemetry.setInvalid();

                        // 如果遥测报头中的 enq_qdepth 大于所设定的阈值(此处为 50)
                        if (hdr.telemetry.enq_qdepth > 50){
                            // 读取最新的发送反馈数据包的时间戳
                            read_feedback_ts();

                            bit<48> backoff;
                            // 随机生成一个阈值 backoff
                            random(backoff, 48w500000, 48w1000000);
                            // 判断当前数据包的入口全局时间戳与最新的发送反馈数据包的时间戳之差是否大于随机生成的阈值
                            if ((standard_metadata.ingress_global_timestamp - meta.feedback_ts) > backoff){
                                // 将当前数据包的入口全局时间戳写入到 feedback_ts 寄存器中对应的元素
	                            feedback_ts.write((bit<32>)meta.feedback_register_index, standard_metadata.ingress_global_timestamp);
	                            
                                // 随机生成一个随机数 probability
                                bit<8> probability;
	                            random(probability, 8w0, 8w3);
                            // 如果 probability 的值为 0, 则克隆该数据包
	                        if (probability == 0) {
                                    clone(CloneType.E2E, 100);
                                }
                            }
                        }
                    }
                }
                else {
                    // 如果遥测报头没有生效, 则表明该交换机为入口交换机
                    // 判断 egress_type 是否为交换机
                    if (meta.egress_type == TYPE_EGRESS_SWITCH){
                        // 生效遥测报头
                        hdr.telemetry.setValid();
                        // 将当前交换机的 enq_qdepth 赋给遥测报头的 enq_qdepth 
                        hdr.telemetry.enq_qdepth = (bit<16>)standard_metadata.enq_qdepth;
                        // ehterType 赋值为 TYPE_TELEMETRY (表示以太网报头的下一层是遥测报头)
                        hdr.ethernet.etherType = TYPE_TELEMETRY;
                        // nextHeaderType 赋值为 TYPE_IPV4 (表示遥测报头的下一层是 IPv4 报头)
                        hdr.telemetry.nextHeaderType = TYPE_IPV4;
                    }
                }
            }
        }
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
              hdr.ipv4.tos,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr},
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