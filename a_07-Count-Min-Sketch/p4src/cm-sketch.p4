/* -*- P4_16 -*- */
#include <core.p4>
#include <v1model.p4>

#include "include/headers.p4"
#include "include/parsers.p4"

/* CONSTANTS */
#define SKETCH_BUCKET_LENGTH 32
#define SKETCH_CELL_BIT_WIDTH 64 //Max counter size

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

    //TODO 4: define N registers
    register<bit<SKETCH_CELL_BIT_WIDTH>>(SKETCH_BUCKET_LENGTH) sketch0;
    register<bit<SKETCH_CELL_BIT_WIDTH>>(SKETCH_BUCKET_LENGTH) sketch1;
    register<bit<SKETCH_CELL_BIT_WIDTH>>(SKETCH_BUCKET_LENGTH) sketch2;

    action drop() {
        mark_to_drop(standard_metadata);
    }

    //TODO 5: Define the sketch_count action
    action sketch_count() { 

        hash(meta.index_sketch0,
             HashAlgorithm.crc32_custom, 
             (bit<16>)0, 
             {hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr,
              hdr.tcp.srcPort,
              hdr.tcp.dstPort,
              hdr.ipv4.protocol},
              (bit<32>)SKETCH_BUCKET_LENGTH);
        
        hash(meta.index_sketch1,
             HashAlgorithm.crc32_custom, 
             (bit<16>)0, 
             {hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr,
              hdr.tcp.srcPort,
              hdr.tcp.dstPort,
              hdr.ipv4.protocol},
              (bit<32>)SKETCH_BUCKET_LENGTH);
        
        hash(meta.index_sketch2,
             HashAlgorithm.crc32_custom, 
             (bit<16>)0, 
             {hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr,
              hdr.tcp.srcPort,
              hdr.tcp.dstPort,
              hdr.ipv4.protocol},
              (bit<32>)SKETCH_BUCKET_LENGTH);
        
        // 将不同寄存器中的相应索引处的值读取并赋给临时存放变量temp_reg_readX
        sketch0.read(meta.value_sketch0, meta.index_sketch0);
        sketch1.read(meta.value_sketch1, meta.index_sketch1);
        sketch2.read(meta.value_sketch2, meta.index_sketch2);
        
        // 将temp_reg_readX的值加1
        meta.value_sketch0 = meta.value_sketch0 + 1;
        meta.value_sketch1 = meta.value_sketch1 + 1;
        meta.value_sketch2 = meta.value_sketch2 + 1;

        // 将修改后的temp_reg_readX的值再写入到寄存器的相应位置中
        sketch0.write(meta.index_sketch0, meta.value_sketch0);
        sketch1.write(meta.index_sketch1, meta.value_sketch1);
        sketch2.write(meta.index_sketch2, meta.value_sketch2);

    }

    //TODO 2: define the set_egress_port action
    action set_egress_port(bit<9> egress_port) {
        standard_metadata.egress_spec = egress_port;
    }

    //TODO 1: define the forwarding table
    table forwarding {
        key = {
            standard_metadata.ingress_port: exact;
        }
        actions = {
            set_egress_port;
            drop;
        }
        size = 1024;
        default_action = drop;
    }


    apply {
        //TODO 6: define the pipeline logic
        if(hdr.ipv4.isValid() && hdr.tcp.isValid()) {
            sketch_count();
        }

        forwarding.apply();
    }
}

/*************************************************************************
****************  E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply {  }
}

/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
     apply {
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